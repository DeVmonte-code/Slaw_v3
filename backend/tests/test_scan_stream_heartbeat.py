"""Tests for /scan/stream heartbeat and resilience behaviour (Task #58).

Drives the ASGI app directly via httpx.AsyncClient so we get real SSE
framing without spinning up a live server.  ``run_benefit_scan`` is
monkeypatched to a short-sleeping stub so the test stays fast while
still verifying that heartbeats fire and stop cleanly.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

import swiss_legal_api.api.main as main_mod
from swiss_legal_api.api.main import app
from swiss_legal_api.config import settings
from swiss_legal_api.schemas import BenefitReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_report() -> BenefitReport:
    return BenefitReport(
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        profile_hash="deadbeef01234567",
        benefits=[],
        suppressed_count=0,
        pending_corpus_backfill=0,
    )


def _valid_profile() -> dict[str, Any]:
    """Minimal valid ContextProfile matching the Luis fixture shape."""
    return {
        "canton": "ZH",
        "language": "de",
        "employment_status": "employee_full_time",
        "employment_start_year": 2018,
        "weekly_hours": 42,
        "housing_status": "tenant",
        "rental_start_year": 2018,
        "lease_reference_rate_tracked": True,
        "rent_chf_monthly": 2400,
        "household_size": 4,
        "children_count": 2,
        "children_ages": [3, 6],
        "marital_status": "married",
        "income_band_chf": "120_200k",
        "has_third_pillar": True,
        "third_pillar_chf_this_year": 7056,
        "business_activity": "none",
        "commute_km_daily": 12,
        "childcare_cost_chf_yearly": 18000,
        "permit_type": "none",
        "nationality_status": "swiss",
        "years_in_switzerland": None,
        "recent_life_events": [],
    }


async def _collect_sse_events(
    client: httpx.AsyncClient,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    """POST to /scan/stream and collect all SSE events until the stream closes."""
    events: list[dict[str, Any]] = []
    async with client.stream(
        "POST",
        "/scan/stream",
        json=profile,
        headers={"Content-Type": "application/json"},
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        buf = ""
        async for chunk in response.aiter_text():
            buf += chunk
            while "\n\n" in buf:
                idx = buf.index("\n\n")
                frame = buf[:idx]
                buf = buf[idx + 2:]
                ev_type = "message"
                data_lines: list[str] = []
                for line in frame.split("\n"):
                    if line.startswith("event:"):
                        ev_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                if data_lines:
                    try:
                        payload = json.loads("\n".join(data_lines))
                    except json.JSONDecodeError:
                        payload = {}
                    events.append({"type": ev_type, "payload": payload})
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_heartbeat_fires_before_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a very short heartbeat interval and a scan that sleeps briefly,
    at least one heartbeat must arrive before the terminal 'complete' event."""
    monkeypatch.setattr(settings, "scan_stream_heartbeat_s", 0.05)

    async def _stub_scan(*args: Any, **kwargs: Any) -> BenefitReport:
        await asyncio.sleep(0.2)
        return _minimal_report()

    monkeypatch.setattr(main_mod, "run_benefit_scan", _stub_scan)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        events = await _collect_sse_events(client, _valid_profile())

    event_types = [e["type"] for e in events]

    assert "heartbeat" in event_types, (
        f"Expected at least one heartbeat event; got: {event_types}"
    )
    assert "complete" in event_types, (
        f"Expected a terminal 'complete' event; got: {event_types}"
    )


@pytest.mark.asyncio
async def test_no_heartbeat_after_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """The heartbeat background task must be stopped before the 'complete'
    event is pushed onto the queue — no heartbeat should appear after the
    terminal event in the event stream."""
    monkeypatch.setattr(settings, "scan_stream_heartbeat_s", 0.05)

    async def _stub_scan(*args: Any, **kwargs: Any) -> BenefitReport:
        await asyncio.sleep(0.15)
        return _minimal_report()

    monkeypatch.setattr(main_mod, "run_benefit_scan", _stub_scan)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        events = await _collect_sse_events(client, _valid_profile())

    event_types = [e["type"] for e in events]

    assert "complete" in event_types
    complete_idx = event_types.index("complete")
    post_complete = event_types[complete_idx + 1:]
    assert "heartbeat" not in post_complete, (
        f"Heartbeat must not appear after 'complete'; "
        f"events after complete: {post_complete}"
    )


@pytest.mark.asyncio
async def test_heartbeat_payload_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each heartbeat event must carry 'type', 'ts', and 'seq' fields."""
    monkeypatch.setattr(settings, "scan_stream_heartbeat_s", 0.05)

    async def _stub_scan(*args: Any, **kwargs: Any) -> BenefitReport:
        await asyncio.sleep(0.15)
        return _minimal_report()

    monkeypatch.setattr(main_mod, "run_benefit_scan", _stub_scan)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        events = await _collect_sse_events(client, _valid_profile())

    heartbeats = [e for e in events if e["type"] == "heartbeat"]
    assert heartbeats, "no heartbeat events in stream"
    for hb in heartbeats:
        p = hb["payload"]
        assert p.get("type") == "heartbeat", f"payload missing type: {p}"
        assert "ts" in p, f"heartbeat missing 'ts': {p}"
        assert "seq" in p, f"heartbeat missing 'seq': {p}"
        assert isinstance(p["seq"], int) and p["seq"] >= 1, (
            f"heartbeat 'seq' must be positive int: {p}"
        )


@pytest.mark.asyncio
async def test_scan_error_does_not_leave_heartbeat_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If run_benefit_scan raises, the stream must still terminate with an
    'error' terminal event and the heartbeat must be stopped (no heartbeat
    after 'error')."""
    monkeypatch.setattr(settings, "scan_stream_heartbeat_s", 0.05)

    async def _failing_scan(*args: Any, **kwargs: Any) -> BenefitReport:
        await asyncio.sleep(0.1)
        raise RuntimeError("simulated scan failure")

    monkeypatch.setattr(main_mod, "run_benefit_scan", _failing_scan)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        events = await _collect_sse_events(client, _valid_profile())

    event_types = [e["type"] for e in events]
    assert "error" in event_types, (
        f"Expected terminal 'error' event on scan failure; got: {event_types}"
    )
    error_idx = event_types.index("error")
    post_error = event_types[error_idx + 1:]
    assert "heartbeat" not in post_error, (
        f"Heartbeat must not appear after 'error'; events after error: {post_error}"
    )
