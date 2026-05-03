"""Smoke test for the Managed Agents environment (Task #35).

Opens one real session against the bootstrapped agent + environment +
vault, asks a trivial Swiss-law question, and asserts that the agent
actually invoked at least one MCP tool. Exits non-zero on any failure
mode the runner distinguishes (config missing, fatal session error,
session terminated, or zero MCP tool uses).

Run after ``python -m swiss_legal_api.managed_agents.bootstrap`` and
after the four ``MANAGED_*`` IDs and ``MCP_BASE_URL`` (or the three
per-server ``MCP_*_URL`` values) are present in the process env.

Usage::

    PYTHONPATH=src python scripts/managed_agents_smoke.py

Exit codes:
    0 — session opened, ≥1 MCP tool used, agent returned text
    1 — config missing (run bootstrap first / set MCP_BASE_URL)
    2 — session opened but no MCP tool was used (mis-wired MCP servers
        or agent declined to use them)
    3 — fatal session error (terminated or non-retryable error)
    4 — unexpected exception
"""

from __future__ import annotations

import asyncio
import logging
import sys

from swiss_legal_api.config import settings
from swiss_legal_api.engine.agent_runner import (
    ManagedAgentsConfigError,
    ManagedAgentsError,
    run_session,
)

PROMPT = (
    "Which Swiss federal SR article governs the standard notice period "
    "an open-ended residential lease tenant must observe to terminate "
    "the contract? Answer with the SR + article number and one short "
    "sentence of reasoning."
)


async def _run() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("managed_agents_smoke")

    log.info(
        "smoke_config agent_id=%s env_id=%s vault_id=%s "
        "mcp_swiss_law=%s mcp_contract_tools=%s mcp_user_context=%s",
        settings.managed_agent_id or "<unset>",
        settings.managed_environment_id or "<unset>",
        settings.managed_vault_id or "<unset>",
        settings.mcp_swiss_law_url or "<unset>",
        settings.mcp_contract_tools_url or "<unset>",
        settings.mcp_user_context_url or "<unset>",
    )

    if not settings.use_managed_agents:
        # The runner doesn't actually consult ``use_managed_agents``
        # (the call sites do), so the smoke test runs regardless.
        # Surface the discrepancy so operators don't think a green
        # smoke means /scan is using the agent.
        log.warning(
            "smoke_use_managed_agents_false — the smoke test still ran "
            "the managed-agents path, but /scan and /chat will keep "
            "using messages.create until USE_MANAGED_AGENTS=1 is set."
        )

    try:
        text, prov = await run_session(
            PROMPT,
            site="smoke",
            metadata={"task_type": "smoke", "user_id": "smoke-test"},
        )
    except ManagedAgentsConfigError as exc:
        log.error("smoke_config_missing %s", exc)
        return 1
    except ManagedAgentsError as exc:
        log.error("smoke_session_failed %s", exc)
        return 3
    except Exception as exc:  # pragma: no cover - defensive
        log.exception("smoke_unexpected exc=%s", type(exc).__name__)
        return 4

    log.info(
        "smoke_result mcp_tool_use_count=%d tool_use_count=%d "
        "agent_backed=%s session_id=%s text_len=%d",
        prov.mcp_tool_use_count,
        prov.tool_use_count,
        prov.agent_backed,
        prov.session_id,
        len(text),
    )
    log.info("smoke_text %s", text.strip()[:300])

    if prov.mcp_tool_use_count <= 0:
        log.error(
            "smoke_no_mcp_tool_use — session opened but the agent did "
            "NOT call any MCP tool. Check that MCP_BASE_URL points at a "
            "publicly-reachable HTTPS host and that the three /mcp/* "
            "mounts return 200 to a streamable-HTTP probe."
        )
        return 2
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
