"""Tests for the deep Qdrant probe used by the lifespan and `/readyz?deep=1`.

Covers all three branches operators care about when bringing a cluster up:
  - reachable + collection seeded with > 0 points  → 200
  - reachable + collection exists but empty        → 503 ("collection_empty")
  - reachable + collection missing                 → 503 ("collection_missing")
  - unreachable                                    → 503 ("qdrant_unreachable")

The lifespan path is exercised indirectly: `_probe_primary_collection` is
the same function the lifespan calls, so verifying its three return shapes
locks the loud-startup-log behaviour. We additionally assert the lifespan
logs `ERROR` for the missing/empty cases.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from swiss_legal_api.api import main as api_main
from swiss_legal_api.api.main import _probe_primary_collection, app
from swiss_legal_api.config import settings


def _fake_qdrant_client_factory(*, collections: list[str], counts: dict[str, int] | None = None):
    """Build a no-network qdrant_client() stand-in.

    `collections` controls which collections appear in get_collections().
    `counts` maps collection name → exact point count returned by count();
    a missing entry raises (mimics Qdrant's 404 on count for an unknown
    collection, though we only count what we know exists).
    """

    counts = counts or {}

    class _Client:
        def get_collections(self):
            return SimpleNamespace(collections=[SimpleNamespace(name=n) for n in collections])

        def count(self, collection_name: str, exact: bool = True):
            if collection_name not in counts:
                raise RuntimeError(f"unknown collection {collection_name}")
            return SimpleNamespace(count=counts[collection_name])

    return lambda: _Client()


def _broken_client_factory():
    class _Boom:
        def get_collections(self):
            raise RuntimeError("connection refused")

        def count(self, *a, **kw):
            raise RuntimeError("connection refused")

    return lambda: _Boom()


# ---------------------------------------------------------------------------
# _probe_primary_collection — direct unit coverage of the three branches.
# ---------------------------------------------------------------------------


def test_probe_returns_ok_when_collection_seeded(monkeypatch):
    monkeypatch.setattr(
        api_main,
        "qdrant_client",
        _fake_qdrant_client_factory(
            collections=[settings.qdrant_collection],
            counts={settings.qdrant_collection: 36},
        ),
    )
    status, n = _probe_primary_collection()
    assert status == "ok"
    assert n == 36


def test_probe_returns_empty_when_collection_has_zero_points(monkeypatch):
    monkeypatch.setattr(
        api_main,
        "qdrant_client",
        _fake_qdrant_client_factory(
            collections=[settings.qdrant_collection],
            counts={settings.qdrant_collection: 0},
        ),
    )
    status, n = _probe_primary_collection()
    assert status == "empty"
    assert n == 0


def test_probe_returns_missing_when_collection_absent(monkeypatch):
    # Cluster exists, but the configured primary collection isn't there
    # (classic "wrong cluster" / "forgot to seed" failure mode).
    monkeypatch.setattr(
        api_main,
        "qdrant_client",
        _fake_qdrant_client_factory(collections=["some_other_collection"]),
    )
    status, n = _probe_primary_collection()
    assert status == "missing"
    assert n is None


def test_probe_propagates_when_qdrant_unreachable(monkeypatch):
    monkeypatch.setattr(api_main, "qdrant_client", _broken_client_factory())
    with pytest.raises(RuntimeError, match="connection refused"):
        _probe_primary_collection()


# ---------------------------------------------------------------------------
# /readyz?deep=1 — HTTP surface of the deep probe.
# ---------------------------------------------------------------------------


async def test_readyz_deep_returns_200_when_collection_seeded(monkeypatch):
    monkeypatch.setattr(
        api_main,
        "qdrant_client",
        _fake_qdrant_client_factory(
            collections=[settings.qdrant_collection],
            counts={settings.qdrant_collection: 36},
        ),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/readyz?deep=1")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["qdrant"] == "reachable"
        assert body["collection"] == "reachable"
        assert body["points"] == 36


async def test_readyz_deep_503_when_collection_missing(monkeypatch):
    monkeypatch.setattr(
        api_main,
        "qdrant_client",
        _fake_qdrant_client_factory(collections=["unrelated_collection"]),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/readyz?deep=1")
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["ok"] is False
        assert detail["qdrant"] == "reachable"
        assert detail["collection"] == "missing"
        assert detail["expected_collection"] == settings.qdrant_collection


async def test_readyz_deep_503_when_collection_empty(monkeypatch):
    monkeypatch.setattr(
        api_main,
        "qdrant_client",
        _fake_qdrant_client_factory(
            collections=[settings.qdrant_collection],
            counts={settings.qdrant_collection: 0},
        ),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/readyz?deep=1")
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["ok"] is False
        assert detail["qdrant"] == "reachable"
        assert detail["collection"] == "empty"
        assert detail["points"] == 0
        assert detail["expected_collection"] == settings.qdrant_collection


async def test_readyz_deep_503_when_qdrant_unreachable(monkeypatch):
    monkeypatch.setattr(api_main, "qdrant_client", _broken_client_factory())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/readyz?deep=1")
        assert r.status_code == 503
        assert r.json()["detail"] == {"ok": False, "qdrant": "unreachable"}


async def test_readyz_default_unchanged_when_collection_empty(monkeypatch):
    """Without ?deep=1, an empty collection MUST NOT fail readiness.

    Locks the public contract: load balancers polling /readyz today don't
    suddenly start failing when this task ships. The deep probe is opt-in
    precisely because bootstrap deployments haven't seeded yet."""
    monkeypatch.setattr(
        api_main,
        "qdrant_client",
        _fake_qdrant_client_factory(
            collections=[settings.qdrant_collection],
            counts={settings.qdrant_collection: 0},
        ),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/readyz")
        assert r.status_code == 200
        assert r.json() == {"ok": True, "qdrant": "reachable"}


async def test_readyz_deep_composes_with_include_curriculum(monkeypatch):
    """Both flags together: 200 only when both checks pass."""
    monkeypatch.setattr(
        api_main,
        "qdrant_client",
        _fake_qdrant_client_factory(
            collections=[
                settings.qdrant_collection,
                settings.curriculum_collection,
            ],
            counts={settings.qdrant_collection: 36},
        ),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/readyz?deep=1&include=curriculum")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["collection"] == "reachable"
        assert body["points"] == 36
        assert body["curriculum"] == "reachable"


# ---------------------------------------------------------------------------
# Lifespan logging — proves a misconfigured cluster fails LOUDLY.
# ---------------------------------------------------------------------------


async def test_lifespan_logs_error_when_collection_missing(monkeypatch, caplog):
    """A misconfigured cluster must surface as ERROR in workflow logs,
    not as a silent INFO. This is the whole point of task #17."""
    monkeypatch.setattr(
        api_main,
        "qdrant_client",
        _fake_qdrant_client_factory(collections=["unrelated"]),
    )
    # The embedder warm-up is unrelated; mock it to keep the test fast and
    # deterministic regardless of whether sentence-transformers is present.
    monkeypatch.setattr(api_main, "get_embedder", lambda: None)

    with caplog.at_level(logging.ERROR, logger=api_main.logger.name):
        async with api_main.lifespan(app):
            pass

    error_msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("MISSING" in m for m in error_msgs), error_msgs


async def test_lifespan_logs_error_when_collection_empty(monkeypatch, caplog):
    monkeypatch.setattr(
        api_main,
        "qdrant_client",
        _fake_qdrant_client_factory(
            collections=[settings.qdrant_collection],
            counts={settings.qdrant_collection: 0},
        ),
    )
    monkeypatch.setattr(api_main, "get_embedder", lambda: None)

    with caplog.at_level(logging.ERROR, logger=api_main.logger.name):
        async with api_main.lifespan(app):
            pass

    error_msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("EMPTY" in m for m in error_msgs), error_msgs


async def test_lifespan_logs_info_when_collection_seeded(monkeypatch, caplog):
    monkeypatch.setattr(
        api_main,
        "qdrant_client",
        _fake_qdrant_client_factory(
            collections=[settings.qdrant_collection],
            counts={settings.qdrant_collection: 36},
        ),
    )
    monkeypatch.setattr(api_main, "get_embedder", lambda: None)

    with caplog.at_level(logging.INFO, logger=api_main.logger.name):
        async with api_main.lifespan(app):
            pass

    msgs = [r.getMessage() for r in caplog.records]
    assert any("36 points" in m for m in msgs), msgs
    # Critically, no ERROR/CRITICAL entries on the happy path.
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
