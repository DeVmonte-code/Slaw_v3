"""Tests for the scheduled benefit sweep (Task #22).

Covers:
* :func:`classify_diff` rules (NEW / GONE / UPDATED across value-change,
  citation-change, Fedlex-amendment branches, and the first-ever-sweep
  edge case).
* :func:`fedlex_changed_articles` snapshot diff (text change,
  paragraph re-numbering ignored, removal counted, missing files
  no-op).
* Storage round-trip (upsert idempotency, retention prune, alert
  insert idempotency, mark-as-read).
* Orchestrator (:func:`sweep_all_users`) end-to-end with a stubbed
  scan_fn — no Anthropic, no Qdrant, no embedder.
* HTTP endpoints via ASGITransport.

All tests run offline. The sqlite store is forced to ``:memory:`` per
test via the ``_isolated_storage`` autouse fixture so they're order-
independent.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from swiss_legal_api import storage
from swiss_legal_api.api.main import app
from swiss_legal_api.engine.sweep import (
    classify_diff,
    fedlex_changed_articles,
    promote_fedlex_snapshot,
    sweep_all_users,
)
from swiss_legal_api.schemas import (
    Benefit,
    BenefitReport,
    Citation,
    ContextProfile,
    Entitlement,
    EstimatedValue,
)

# ----- Fixtures ----------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path: Path) -> Iterator[None]:
    # Use a tmp file rather than ``:memory:`` so the connection survives
    # being shared across the FastAPI threadpool + test thread without
    # the in-memory DB resetting between connections (sqlite ``:memory:``
    # is per-connection unless you use the URI form).
    storage.set_db_path(tmp_path / "sweep.db")
    yield
    storage.reset_for_tests()


def _profile(canton: str = "ZH") -> ContextProfile:
    return ContextProfile(
        canton=canton,  # type: ignore[arg-type]
        employment_status="employee_full_time",
        housing_status="tenant",
        marital_status="single",
        income_band_chf="80_120k",
    )


def _citation(sr: str, art: str, *, quote: str = "test quote") -> Citation:
    return Citation(
        sr_number=sr,
        article=art,
        language="de",
        quote_under_15_words=quote,
    )


def _benefit(
    eid: str,
    *,
    value_min: float = 100,
    value_max: float = 500,
    citations: list[Citation] | None = None,
) -> Benefit:
    return Benefit(
        entitlement_id=eid,
        title=f"Benefit {eid}",
        category="tax_deduction",
        estimated_value_chf=EstimatedValue(min=value_min, max=value_max, per="year"),
        confidence=0.9,
        citations=citations or [_citation("220", "1")],
        evidence=[],
        required_action="tax_declaration_field",
        llm_reasoning="stub",
    )


def _report(
    benefits: list[Benefit], *, generated_at: str = "2026-05-02T10:00:00Z",
) -> BenefitReport:
    return BenefitReport(
        generated_at=generated_at,
        profile_hash="hash-" + str(len(benefits)),
        benefits=benefits,
        suppressed_count=0,
    )


# ----- classify_diff -----------------------------------------------------


class TestClassifyDiff:
    def test_first_sweep_emits_new_for_every_benefit(self):
        report = _report([_benefit("a"), _benefit("b")])
        alerts = classify_diff(user_id="u", previous=None, current=report)
        assert {a.kind for a in alerts} == {"NEW"}
        assert {a.entitlement_id for a in alerts} == {"a", "b"}
        # Ordering is deterministic so snapshot tests are stable.
        assert [a.entitlement_id for a in alerts] == ["a", "b"]

    def test_no_change_yields_no_alerts(self):
        prev = _report([_benefit("a")], generated_at="2026-05-01T10:00:00Z")
        curr = _report([_benefit("a")])
        assert classify_diff(user_id="u", previous=prev, current=curr) == []

    def test_value_change_emits_updated_with_previous_value(self):
        prev = _report(
            [_benefit("a", value_min=100, value_max=200)],
            generated_at="2026-05-01T10:00:00Z",
        )
        curr = _report([_benefit("a", value_min=300, value_max=400)])
        alerts = classify_diff(user_id="u", previous=prev, current=curr)
        assert len(alerts) == 1
        a = alerts[0]
        assert a.kind == "UPDATED"
        assert a.payload.estimated_value_chf_min == 300
        assert a.payload.previous_estimated_value_chf_min == 100
        assert a.payload.previous_estimated_value_chf_max == 200

    def test_citation_set_change_emits_updated(self):
        prev = _report(
            [_benefit("a", citations=[_citation("220", "1")])],
            generated_at="2026-05-01T10:00:00Z",
        )
        curr = _report(
            [_benefit("a", citations=[_citation("220", "2")])],
        )
        alerts = classify_diff(user_id="u", previous=prev, current=curr)
        assert [a.kind for a in alerts] == ["UPDATED"]

    def test_paragraph_quote_only_change_does_not_alert(self):
        # Same SR + article, different (sub-15-word) quote: not a real
        # entitlement change. Without this guard a Fedlex re-embedding
        # that picks a different paragraph for the same article would
        # spam every user with a spurious UPDATE.
        prev = _report(
            [_benefit("a", citations=[_citation("220", "1", quote="alpha")])],
            generated_at="2026-05-01T10:00:00Z",
        )
        curr = _report(
            [_benefit("a", citations=[_citation("220", "1", quote="bravo")])],
        )
        assert classify_diff(user_id="u", previous=prev, current=curr) == []

    def test_gone_alert_when_entitlement_drops(self):
        prev = _report(
            [_benefit("a"), _benefit("b")], generated_at="2026-05-01T10:00:00Z"
        )
        curr = _report([_benefit("a")])
        alerts = classify_diff(user_id="u", previous=prev, current=curr)
        assert [(a.kind, a.entitlement_id) for a in alerts] == [("GONE", "b")]

    def test_fedlex_amendment_emits_updated_even_when_value_unchanged(self):
        # Identical reports — but the user cites SR 220 art 270, which
        # appears in changed_articles. The orchestrator must surface
        # this as UPDATED so the inbox shows "your cited article was
        # amended" copy.
        same = _report(
            [_benefit("a", citations=[_citation("220", "270", quote="rent quote")])],
            generated_at="2026-05-02T10:00:00Z",
        )
        prev = _report(
            [_benefit("a", citations=[_citation("220", "270", quote="rent quote")])],
            generated_at="2026-05-01T10:00:00Z",
        )
        alerts = classify_diff(
            user_id="u",
            previous=prev,
            current=same,
            changed_articles={("220", "270"): "2026-01-15"},
        )
        assert len(alerts) == 1
        a = alerts[0]
        assert a.kind == "UPDATED"
        assert a.payload.changed_citations == ["SR220/Art270"]
        assert a.payload.fedlex_amendment_date == "2026-01-15"

    def test_alert_id_is_deterministic(self):
        # Re-running the same diff must yield the same alert_id so
        # storage.insert_alert dedupes correctly.
        curr = _report([_benefit("a")])
        first = classify_diff(user_id="u", previous=None, current=curr)
        second = classify_diff(user_id="u", previous=None, current=curr)
        assert [a.alert_id for a in first] == [a.alert_id for a in second]


# ----- fedlex_changed_articles -------------------------------------------


def _write_snapshot(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows))


class TestFedlexDiff:
    def test_text_change_detected(self, tmp_path: Path):
        prev = tmp_path / "p.json"
        curr = tmp_path / "c.json"
        _write_snapshot(prev, [
            {"sr_number": "220", "article": "270", "paragraph": "1", "text": "old"},
        ])
        _write_snapshot(curr, [
            {
                "sr_number": "220", "article": "270", "paragraph": "1",
                "text": "new", "effective_date": "2026-03-01",
            },
        ])
        assert fedlex_changed_articles(curr, prev) == {("220", "270"): "2026-03-01"}

    def test_paragraph_renumbering_with_same_text_ignored(self, tmp_path: Path):
        # Fedlex sometimes reshuffles para_Y while text stays. The
        # diff must aggregate all paragraphs of an article before
        # hashing — otherwise we'd ship a false-positive amendment
        # storm on every Fedlex republication.
        prev = tmp_path / "p.json"
        curr = tmp_path / "c.json"
        _write_snapshot(prev, [
            {"sr_number": "220", "article": "270", "paragraph": "1", "text": "alpha"},
            {"sr_number": "220", "article": "270", "paragraph": "2", "text": "bravo"},
        ])
        _write_snapshot(curr, [
            {"sr_number": "220", "article": "270", "paragraph": "alt-2", "text": "bravo"},
            {"sr_number": "220", "article": "270", "paragraph": "alt-1", "text": "alpha"},
        ])
        assert fedlex_changed_articles(curr, prev) == {}

    def test_repeal_counted_as_change(self, tmp_path: Path):
        prev = tmp_path / "p.json"
        curr = tmp_path / "c.json"
        _write_snapshot(prev, [
            {
                "sr_number": "220", "article": "270", "paragraph": "1",
                "text": "x", "effective_date": "2020-01-01",
            },
        ])
        _write_snapshot(curr, [])
        # Repeal carries the previous snapshot's date so the UI can
        # still render "amended on YYYY-MM-DD" for the GONE case.
        assert fedlex_changed_articles(curr, prev) == {("220", "270"): "2020-01-01"}

    def test_missing_files_returns_empty(self, tmp_path: Path):
        # First-ever sweep has no baseline: don't false-positive every
        # article as "changed".
        assert fedlex_changed_articles(tmp_path / "x.json", tmp_path / "y.json") == {}

    def test_promote_copies_current_to_previous(self, tmp_path: Path):
        cur = tmp_path / "c.json"
        prev = tmp_path / "p.json"
        _write_snapshot(cur, [{"sr_number": "1", "article": "1", "text": "x"}])
        promote_fedlex_snapshot(cur, prev)
        assert json.loads(prev.read_text()) == json.loads(cur.read_text())


# ----- Storage -----------------------------------------------------------


class TestStorage:
    def test_upsert_user_is_idempotent_and_preserves_created_at(self):
        first = storage.upsert_user("u1", _profile(), notify_enabled=True)
        second = storage.upsert_user("u1", _profile("BE"), notify_enabled=False)
        assert first.created_at == second.created_at
        assert second.profile.canton == "BE"
        assert second.notify_enabled is False
        # last_seen_at must advance (or stay equal — second-precision)
        assert second.last_seen_at >= first.last_seen_at

    def test_list_users_filters_notify_enabled(self):
        storage.upsert_user("on", _profile(), notify_enabled=True)
        storage.upsert_user("off", _profile(), notify_enabled=False)
        all_users = storage.list_users()
        opted_in = storage.list_users(only_notify_enabled=True)
        assert {u.user_id for u in all_users} == {"on", "off"}
        assert {u.user_id for u in opted_in} == {"on"}

    def test_retention_prune_keeps_most_recent(self):
        storage.upsert_user("u1", _profile(), notify_enabled=True)
        for i in range(5):
            storage.insert_scan(
                "u1", _report([_benefit("a")], generated_at=f"2026-05-0{i+1}T10:00:00Z")
            )
        deleted = storage.prune_scans("u1", keep=2)
        assert deleted == 3
        # Latest survives.
        latest = storage.latest_scan("u1")
        assert latest is not None
        assert latest.generated_at == "2026-05-05T10:00:00Z"

    def test_insert_alert_is_idempotent(self):
        storage.upsert_user("u1", _profile(), notify_enabled=True)
        report = _report([_benefit("a")])
        alerts = classify_diff(user_id="u1", previous=None, current=report)
        assert storage.insert_alert(alerts[0]) is True
        assert storage.insert_alert(alerts[0]) is False  # second call no-op
        assert len(storage.list_alerts("u1")) == 1

    def test_mark_alert_read(self):
        storage.upsert_user("u1", _profile(), notify_enabled=True)
        report = _report([_benefit("a")])
        alert = classify_diff(user_id="u1", previous=None, current=report)[0]
        storage.insert_alert(alert)
        assert storage.mark_alert_read("u1", alert.alert_id) is True
        # Second call returns False because already-read alerts are excluded.
        assert storage.mark_alert_read("u1", alert.alert_id) is False
        assert storage.mark_alert_read("other", alert.alert_id) is False
        unread = storage.list_alerts("u1", unread_only=True)
        assert unread == []


# ----- Orchestrator ------------------------------------------------------


@pytest.mark.asyncio
async def test_sweep_all_users_end_to_end(tmp_path: Path):
    storage.upsert_user("u1", _profile(), notify_enabled=True)
    storage.upsert_user("u-off", _profile(), notify_enabled=False)

    # First sweep: returns one benefit. Second: value changes.
    counter = {"n": 0}

    async def stub_scan(profile: ContextProfile, catalog: list[Entitlement]) -> BenefitReport:
        counter["n"] += 1
        if counter["n"] == 1:
            return _report(
                [_benefit("a", value_min=100, value_max=200)],
                generated_at="2026-05-01T10:00:00Z",
            )
        return _report(
            [_benefit("a", value_min=300, value_max=400)],
            generated_at="2026-05-02T10:00:00Z",
        )

    # Empty Fedlex snapshot pair so the diff is value-only.
    cur = tmp_path / "cur.json"
    prev = tmp_path / "prev.json"
    cur.write_text("[]")
    prev.write_text("[]")

    summary1 = await sweep_all_users(
        catalog=[], scan_fn=stub_scan, fedlex_current=cur, fedlex_previous=prev,
    )
    assert summary1["users"] == 1  # only u1 (notify-enabled)
    assert summary1["failures"] == 0
    assert summary1["alerts_inserted"] == 1  # NEW for "a"

    summary2 = await sweep_all_users(
        catalog=[], scan_fn=stub_scan, fedlex_current=cur, fedlex_previous=prev,
    )
    assert summary2["alerts_inserted"] == 1  # UPDATED

    alerts = storage.list_alerts("u1")
    assert sorted(a.kind for a in alerts) == ["NEW", "UPDATED"]
    # Opted-out user must not have been scanned at all.
    assert storage.latest_scan("u-off") is None


@pytest.mark.asyncio
async def test_sweep_force_rescan_via_fedlex_change(tmp_path: Path):
    """A user whose previous scan cited an article that subsequently
    changed in Fedlex must get an UPDATED alert, even when the new
    scan returns an identical report."""
    storage.upsert_user("u1", _profile(), notify_enabled=True)

    cited = _citation("220", "270", quote="rent")
    report = _report(
        [_benefit("a", citations=[cited])],
        generated_at="2026-05-01T10:00:00Z",
    )

    # Seed a previous scan + a previous Fedlex snapshot.
    storage.insert_scan("u1", report)
    prev = tmp_path / "prev.json"
    cur = tmp_path / "cur.json"
    _write_snapshot(prev, [
        {"sr_number": "220", "article": "270", "paragraph": "1", "text": "old text"},
    ])
    _write_snapshot(cur, [
        {"sr_number": "220", "article": "270", "paragraph": "1", "text": "AMENDED"},
    ])

    async def stub_scan(profile: ContextProfile, catalog: list[Entitlement]) -> BenefitReport:
        # Same shape but with a fresh generated_at so the storage key differs.
        return _report(
            [_benefit("a", citations=[cited])],
            generated_at="2026-05-02T10:00:00Z",
        )

    summary = await sweep_all_users(
        catalog=[], scan_fn=stub_scan, fedlex_current=cur, fedlex_previous=prev,
    )
    assert summary["changed_articles"] == 1
    alerts = storage.list_alerts("u1")
    assert len(alerts) == 1
    assert alerts[0].kind == "UPDATED"
    assert alerts[0].payload.changed_citations == ["SR220/Art270"]

    # Snapshot must have been promoted so the next sweep doesn't
    # re-fire the same alert.
    assert prev.read_text() == cur.read_text()


@pytest.mark.asyncio
async def test_sweep_does_not_promote_snapshot_when_a_user_fails(tmp_path: Path):
    storage.upsert_user("u-good", _profile(), notify_enabled=True)
    storage.upsert_user("u-bad", _profile(), notify_enabled=True)

    async def stub_scan(profile: ContextProfile, catalog: list[Entitlement]) -> BenefitReport:
        if profile.canton == "ZH":  # both stubs are ZH, second crashes
            stub_scan.calls = getattr(stub_scan, "calls", 0) + 1  # type: ignore[attr-defined]
            if stub_scan.calls == 2:  # type: ignore[attr-defined]
                raise RuntimeError("boom")
        return _report([_benefit("a")])

    cur = tmp_path / "cur.json"
    prev = tmp_path / "prev.json"
    _write_snapshot(cur, [{"sr_number": "1", "article": "1", "text": "x"}])
    _write_snapshot(prev, [{"sr_number": "1", "article": "1", "text": "y"}])

    pre_prev = prev.read_text()
    summary = await sweep_all_users(
        catalog=[], scan_fn=stub_scan, fedlex_current=cur, fedlex_previous=prev,
    )
    assert summary["failures"] == 1
    # Snapshot NOT promoted: next run still sees the same delta and can
    # retry the failed user without losing the Fedlex change.
    assert prev.read_text() == pre_prev


# ----- HTTP endpoints ---------------------------------------------------


@pytest.mark.asyncio
async def test_profile_endpoint_round_trip():
    body = {
        "profile": _profile().model_dump(mode="json"),
        "notify_enabled": True,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/users/abc/profile", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user_id"] == "abc"
        assert data["notify_enabled"] is True

        r = await c.get("/users/abc/profile")
        assert r.status_code == 200

        r = await c.get("/users/abc/scans/latest")
        assert r.status_code == 404  # no sweep has run yet

        r = await c.get("/users/abc/alerts")
        assert r.status_code == 200
        assert r.json() == {"alerts": []}


@pytest.mark.asyncio
async def test_alert_inbox_lists_and_marks_read():
    # Seed via storage directly so we don't depend on a live sweep.
    storage.upsert_user("u1", _profile(), notify_enabled=True)
    report = _report([_benefit("a")])
    storage.insert_scan("u1", report)
    alert = classify_diff(user_id="u1", previous=None, current=report)[0]
    storage.insert_alert(alert)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/users/u1/scans/latest")
        assert r.status_code == 200
        assert r.json()["benefits"][0]["entitlement_id"] == "a"

        r = await c.get("/users/u1/alerts?unread_only=true")
        assert r.status_code == 200
        assert len(r.json()["alerts"]) == 1

        r = await c.post(f"/users/u1/alerts/{alert.alert_id}/read")
        assert r.status_code == 204

        r = await c.get("/users/u1/alerts?unread_only=true")
        assert r.json() == {"alerts": []}

        # Idempotent: re-marking a read alert is still 204.
        r = await c.post(f"/users/u1/alerts/{alert.alert_id}/read")
        assert r.status_code == 204

        # 404 only when the alert truly isn't visible to this user.
        r = await c.post("/users/u1/alerts/does-not-exist/read")
        assert r.status_code == 404
