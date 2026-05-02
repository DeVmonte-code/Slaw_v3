"""Managed-agents session runner (Task #26).

Public surface: :func:`run_session`, which the call sites in
``engine/verify.py`` and ``api/chat.py`` invoke instead of
``messages.create`` when ``settings.use_managed_agents`` is True.

Per the design note (and the docs under ``backend/doc/Claude Managed
Agents overview/``):

1. ``POST /v1/sessions`` to launch a session pinned to the
   pre-provisioned agent + environment + vault.
2. Open the SSE stream at ``GET /v1/sessions/{id}/stream`` BEFORE
   sending the first user event, otherwise events that fire between
   ``POST /events`` and the stream subscription are lost (the stream
   only delivers events emitted after it opens).
3. Send a ``user.message`` event with the task brief.
4. Consume events until ``session.status_idle`` (success) or
   ``session.status_terminated`` / ``session.error`` with a fatal
   ``retry_status`` (failure).
5. Build the ``(text, AgentProvenance)`` tuple from the observed
   ``agent.message`` text and the count of ``agent.tool_use`` /
   ``agent.mcp_tool_use`` events.

Auditor contract: the returned :class:`AgentProvenance` has
``call_kind="sessions.events"`` always, and ``agent_backed=True`` iff
the session actually invoked at least one tool — exactly the truth
function the schema's ``model_validator`` enforces in #25.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx

from ..config import settings
from ..schemas import AgentProvenance

logger = logging.getLogger(__name__)


class ManagedAgentsError(RuntimeError):
    """Raised on unrecoverable session failures (terminated / fatal error).

    The call sites translate this back to the same
    short-circuit/retry shape the messages.create path uses, so a
    managed-agents outage degrades the same way a Claude API outage
    already does.
    """


class ManagedAgentsConfigError(RuntimeError):
    """Raised when ``use_managed_agents=True`` but IDs are missing.

    Fail loudly: silently degrading to messages.create would defeat
    the whole audit. The /readyz handler can catch this and refuse to
    serve.
    """


@dataclass
class _RunAccumulator:
    """Collects agent output and tool-use evidence as the SSE stream is consumed."""

    text_parts: list[str] = field(default_factory=list)
    tool_use_count: int = 0
    mcp_tool_use_count: int = 0
    mcp_servers_invoked: set[str] = field(default_factory=set)
    last_error: dict[str, object] | None = None
    terminated: bool = False

    @property
    def text(self) -> str:
        return "".join(self.text_parts)


def _require_config() -> None:
    """Validate that the bootstrap has populated the required IDs."""
    missing = [
        name
        for name, value in (
            ("managed_agent_id", settings.managed_agent_id),
            ("managed_environment_id", settings.managed_environment_id),
        )
        if not value
    ]
    if missing:
        raise ManagedAgentsConfigError(
            f"use_managed_agents=True but missing settings: {', '.join(missing)}. "
            "Run `python -m swiss_legal_api.managed_agents.bootstrap` first."
        )


def _headers() -> dict[str, str]:
    return {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": settings.managed_agents_beta,
        "content-type": "application/json",
    }


def _tools_offered() -> list[str]:
    """The toolset names declared on the agent at bootstrap time.

    Mirrored here so the provenance record carries the contract even
    when the runner is invoked offline (e.g. in tests with a mocked
    transport). Stays in sync with ``managed_agents/bootstrap.py``.
    """
    offered = ["agent_toolset_20260401"]
    if settings.mcp_swiss_law_url:
        offered.append("swiss-law-retrieval-mcp")
    if settings.mcp_contract_tools_url:
        offered.append("swiss-contract-tools-mcp")
    if settings.mcp_user_context_url:
        offered.append("swiss-user-context-mcp")
    return offered


async def _create_session(client: httpx.AsyncClient, *, metadata: dict[str, str]) -> str:
    """``POST /v1/sessions`` pinned to the bootstrapped agent version."""
    payload: dict[str, object] = {
        "agent": (
            {
                "type": "agent",
                "id": settings.managed_agent_id,
                "version": settings.managed_agent_version,
            }
            if settings.managed_agent_version > 0
            else settings.managed_agent_id
        ),
        "environment_id": settings.managed_environment_id,
        "metadata": metadata,
    }
    if settings.managed_vault_id:
        payload["vault_ids"] = [settings.managed_vault_id]
    resp = await client.post("/v1/sessions", json=payload, headers=_headers())
    resp.raise_for_status()
    return str(resp.json()["id"])


async def _send_user_message(
    client: httpx.AsyncClient, session_id: str, text: str
) -> None:
    """Send the task brief as a ``user.message`` event."""
    resp = await client.post(
        f"/v1/sessions/{session_id}/events",
        json={
            "events": [
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": text}],
                }
            ]
        },
        headers=_headers(),
    )
    resp.raise_for_status()


async def _stream_events(
    client: httpx.AsyncClient,
    session_id: str,
    ready: asyncio.Event,
) -> AsyncIterator[dict[str, object]]:
    """Yield each parsed SSE ``data: {json}`` event from the session stream.

    ``ready`` is set the instant the server has accepted the GET and we
    hold a streaming response — i.e. the subscription is established
    server-side. The caller waits on ``ready`` before sending the
    ``user.message`` event so the docs' "open the stream first"
    contract is satisfied deterministically (not via a scheduling hint).
    """
    async with client.stream(
        "GET",
        f"/v1/sessions/{session_id}/stream",
        headers={**_headers(), "Accept": "text/event-stream"},
        timeout=settings.managed_session_timeout_s,
    ) as resp:
        resp.raise_for_status()
        # Subscription is now live — release the producer to send events.
        ready.set()
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[len("data:") :].strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                # Defensive: log & skip malformed frames rather than
                # blowing up the whole session.
                logger.warning("agent_stream_bad_frame session_id=%s", session_id)


def _ingest_event(event: dict[str, object], acc: _RunAccumulator) -> bool:
    """Update the accumulator from one event. Return True iff the stream is done."""
    et = event.get("type")
    if et == "agent.message":
        content = event.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    acc.text_parts.append(str(block.get("text", "")))
    elif et == "agent.tool_use":
        acc.tool_use_count += 1
    elif et == "agent.mcp_tool_use":
        acc.mcp_tool_use_count += 1
        server = event.get("server_name") or event.get("mcp_server_name")
        if isinstance(server, str) and server:
            acc.mcp_servers_invoked.add(server)
    elif et == "session.status_idle":
        return True
    elif et == "session.status_terminated":
        acc.terminated = True
        return True
    elif et == "session.error":
        err = event.get("error")
        if isinstance(err, dict):
            acc.last_error = err
            # Fatal vs transient: only stop the stream when the server
            # tells us no retry is coming.
            retry_status = err.get("retry_status")
            if retry_status in (None, "no_retry", "fatal"):
                return True
    return False


async def _consume(
    client: httpx.AsyncClient,
    session_id: str,
    ready: asyncio.Event,
) -> _RunAccumulator:
    acc = _RunAccumulator()
    async for event in _stream_events(client, session_id, ready):
        if _ingest_event(event, acc):
            break
    return acc


async def run_session(
    user_message: str,
    *,
    site: str,
    metadata: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[str, AgentProvenance]:
    """Run one managed-agents session and return ``(text, AgentProvenance)``.

    Same shape as the messages.create path so the call sites swap with
    a one-line conditional. ``transport`` is exposed for the unit tests
    so they can plug in a ``MockTransport`` and replay a canned SSE
    stream without hitting the real Anthropic API.
    """
    _require_config()
    started = time.perf_counter()
    md = {
        "task_type": site,
        **(metadata or {}),
    }

    async with httpx.AsyncClient(
        base_url=settings.anthropic_api_base,
        transport=transport,
        timeout=settings.managed_session_timeout_s,
    ) as client:
        session_id = await _create_session(client, metadata=md)
        # Open the stream first, then send the user message — per the
        # docs, events emitted before the subscription are NOT replayed.
        # `ready` is set inside _stream_events the instant the GET
        # response is open, giving us a deterministic stream-ready
        # barrier instead of a scheduling hint.
        ready = asyncio.Event()
        consumer_task = asyncio.create_task(
            _consume(client, session_id, ready)
        )
        try:
            try:
                await asyncio.wait_for(
                    ready.wait(), timeout=settings.managed_session_timeout_s
                )
            except TimeoutError as exc:
                consumer_task.cancel()
                raise ManagedAgentsError(
                    f"stream_open_timeout session_id={session_id}"
                ) from exc
            await _send_user_message(client, session_id, user_message)
            try:
                acc = await asyncio.wait_for(
                    consumer_task, timeout=settings.managed_session_timeout_s
                )
            except TimeoutError as exc:
                consumer_task.cancel()
                raise ManagedAgentsError(
                    f"session_timeout session_id={session_id}"
                ) from exc
        except Exception:
            if not consumer_task.done():
                consumer_task.cancel()
            raise

    latency_ms = int((time.perf_counter() - started) * 1000)

    if acc.terminated:
        raise ManagedAgentsError(
            f"session_terminated session_id={session_id} error={acc.last_error}"
        )
    if acc.last_error is not None and not acc.text_parts:
        raise ManagedAgentsError(
            f"session_error session_id={session_id} error={acc.last_error}"
        )

    tool_count = acc.tool_use_count + acc.mcp_tool_use_count
    prov = AgentProvenance(
        call_kind="sessions.events",
        agent_backed=tool_count > 0,
        model=settings.claude_model,
        latency_ms=latency_ms,
        agent_id=settings.managed_agent_id,
        agent_version=settings.managed_agent_version or None,
        session_id=session_id,
        environment_id=settings.managed_environment_id,
        tools_offered=_tools_offered(),
        tool_use_count=acc.tool_use_count,
        mcp_tool_use_count=acc.mcp_tool_use_count,
        mcp_servers_invoked=sorted(acc.mcp_servers_invoked),
    )
    logger.info("%s", prov.to_log_fields(site=site))
    return acc.text, prov
