import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from swiss_legal_api.api import main as api_main
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


async def test_readyz_default_returns_ok_when_qdrant_reachable(monkeypatch):
    """Without ?include=curriculum, /readyz only checks Qdrant ping.

    Locks the existing public contract: load balancers should be able to
    poll /readyz without depending on the curriculum collection being
    seeded (it isn't on bootstrap deployments)."""

    def _fake_client():
        return SimpleNamespace(
            get_collections=lambda: SimpleNamespace(collections=[SimpleNamespace(name="swiss_law")])
        )

    monkeypatch.setattr(api_main, "qdrant_client", _fake_client)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/readyz")
        assert r.status_code == 200
        assert r.json() == {"ok": True, "qdrant": "reachable"}


async def test_readyz_curriculum_branch_503_when_collection_missing(monkeypatch):
    """?include=curriculum must 503 when Qdrant is up but doctrine collection
    is absent — explicit signal for deployments that opt into doctrine."""
    from swiss_legal_api.config import settings

    def _fake_client():
        return SimpleNamespace(
            get_collections=lambda: SimpleNamespace(collections=[SimpleNamespace(name="swiss_law")])
        )

    monkeypatch.setattr(api_main, "qdrant_client", _fake_client)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/readyz?include=curriculum")
        assert r.status_code == 503
        body = r.json()["detail"]
        assert body["ok"] is False
        assert body["qdrant"] == "reachable"
        assert body["curriculum"] == "missing"
        assert body["expected_collection"] == settings.curriculum_collection


async def test_readyz_curriculum_branch_200_when_collection_present(monkeypatch):
    """?include=curriculum must 200 when both swiss_law and curriculum
    collections are present — proves the happy path doesn't accidentally
    require additional state."""
    from swiss_legal_api.config import settings

    def _fake_client():
        return SimpleNamespace(
            get_collections=lambda: SimpleNamespace(
                collections=[
                    SimpleNamespace(name="swiss_law"),
                    SimpleNamespace(name=settings.curriculum_collection),
                ]
            )
        )

    monkeypatch.setattr(api_main, "qdrant_client", _fake_client)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/readyz?include=curriculum")
        assert r.status_code == 200
        assert r.json() == {
            "ok": True,
            "qdrant": "reachable",
            "curriculum": "reachable",
        }


async def test_readyz_503_when_qdrant_unreachable(monkeypatch):
    """Both default and curriculum branches must 503 if Qdrant is down."""

    def _broken_client():
        class _Boom:
            def get_collections(self):
                raise RuntimeError("connection refused")

        return _Boom()

    monkeypatch.setattr(api_main, "qdrant_client", _broken_client)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/readyz")
        assert r.status_code == 503
        assert r.json()["detail"] == {"ok": False, "qdrant": "unreachable"}


@pytest.mark.skipif(
    not (os.getenv("ANTHROPIC_API_KEY") and os.getenv("QDRANT_URL")),
    reason="requires live secrets",
)
async def test_scan_endpoint_live():
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "luis_profile.json"
    payload = json.loads(fixture.read_text())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", timeout=180) as c:
        r = await c.post("/scan", json=payload)
        assert r.status_code == 200
        report = r.json()
        assert len(report["benefits"]) >= 5
        ids = {b["entitlement_id"] for b in report["benefits"]}
        assert "rent_reduction_reference_rate" in ids
        assert "childcare_cost_deduction" in ids
