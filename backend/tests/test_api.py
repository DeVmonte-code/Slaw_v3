import json
import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from swiss_legal_api.api.main import app


async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health")
        assert r.status_code == 200
        assert r.json() == {"ok": True}


async def test_openapi_schema_available():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert "paths" in schema
        assert "/scan" in schema["paths"]
        assert "/chat" in schema["paths"]


@pytest.mark.skipif(
    not (os.getenv("ANTHROPIC_API_KEY") and os.getenv("QDRANT_URL")),
    reason="requires live secrets",
)
async def test_scan_endpoint_live():
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "luis_profile.json"
    payload = json.loads(fixture.read_text())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t", timeout=180
    ) as c:
        r = await c.post("/scan", json=payload)
        assert r.status_code == 200
        report = r.json()
        assert len(report["benefits"]) >= 5
        ids = {b["entitlement_id"] for b in report["benefits"]}
        assert "rent_reduction_reference_rate" in ids
        assert "childcare_cost_deduction" in ids
