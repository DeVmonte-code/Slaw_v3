"""One-shot bootstrap that provisions agent + environment + vault.

Run once per cluster::

    python -m swiss_legal_api.managed_agents.bootstrap

Re-runnable: uses the docs' update semantics
(``PUT /v1/agents/{id}`` with the current ``version``) to bump
versions on edit instead of duplicating. Writes the resulting IDs
back to ``backend/.env`` so the next ``settings = Settings()`` picks
them up — operators can then flip ``use_managed_agents=true`` and
restart.

The system prompt below preserves the citation contract and the FADP
rules from ``engine/verify.py:SYSTEM`` so the managed-agents path
ships with the same legal posture as the messages.create baseline.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are SwissLegalBenefitScanner, a legal-aid research agent.

Mandate:
- For each request, identify the Swiss federal SR (Systematische
  Rechtssammlung) article — and any cantonal article when relevant —
  that supports or rejects the user's claim.
- Use the swiss-law-retrieval-mcp tools (`qdrant_search`,
  `fetch_article_by_sr`, `list_citations`) for every retrieval.
- Use swiss-contract-tools-mcp (`verify_entitlement`,
  `run_benefit_scan`) for analysis. Use swiss-user-context-mcp
  (`read_user_docs`, `update_user_profile`) only when the user message
  explicitly references a user_id.

Authoritative-source policy (FADP-aligned):
- DE/FR/IT Fedlex chunks are authoritative; EN is a courtesy
  translation only. When only translations are available, cap your
  confidence at 0.75 and say so in the reasoning.
- Never cite doctrine or supporting commentary as primary authority.
  Citations are SR + article only.
- If retrieval returns no chunk above similarity threshold, refuse:
  supports=false with a clear reason. Do NOT hallucinate article text.

Output:
- Every final answer is valid JSON of shape
  {"supports": bool, "confidence": 0..1, "reasoning": string,
  "best_quote": string (<=15 words)}.
- The "best_quote" must come from a retrieved authoritative chunk.
"""


# Per the design note: pre-built toolset (file/web_search/web_fetch as
# always_allow, bash as always_ask) plus three MCP toolsets with
# sane defaults. Read-only retrieval = always_allow, write-ish or
# Claude-call-triggering = always_ask.
def _agent_payload() -> dict[str, Any]:
    tools: list[dict[str, Any]] = [
        {
            "type": "agent_toolset_20260401",
            "default_config": {
                "permission_policies": {
                    "file": {"type": "always_allow"},
                    "web_search": {"type": "always_allow"},
                    "web_fetch": {"type": "always_allow"},
                    "bash": {"type": "always_ask"},
                }
            },
        }
    ]
    mcp_servers: list[dict[str, str]] = []
    if settings.mcp_swiss_law_url:
        mcp_servers.append(
            {
                "type": "url",
                "name": "swiss-law-retrieval-mcp",
                "url": settings.mcp_swiss_law_url,
            }
        )
        tools.append(
            {
                "type": "mcp_toolset",
                "mcp_server_name": "swiss-law-retrieval-mcp",
                "default_config": {
                    "permission_policy": {"type": "always_allow"}
                },
            }
        )
    if settings.mcp_contract_tools_url:
        mcp_servers.append(
            {
                "type": "url",
                "name": "swiss-contract-tools-mcp",
                "url": settings.mcp_contract_tools_url,
            }
        )
        tools.append(
            {
                "type": "mcp_toolset",
                "mcp_server_name": "swiss-contract-tools-mcp",
                "default_config": {
                    "permission_policy": {"type": "always_ask"}
                },
            }
        )
    if settings.mcp_user_context_url:
        mcp_servers.append(
            {
                "type": "url",
                "name": "swiss-user-context-mcp",
                "url": settings.mcp_user_context_url,
            }
        )
        tools.append(
            {
                "type": "mcp_toolset",
                "mcp_server_name": "swiss-user-context-mcp",
                "default_config": {
                    "permission_policy": {"type": "always_ask"}
                },
            }
        )
    return {
        "name": "SwissLegalBenefitScanner",
        "model": settings.claude_model,
        "system": SYSTEM_PROMPT,
        "tools": tools,
        "mcp_servers": mcp_servers,
        "metadata": {"app": "slaw_v3", "task": "26"},
    }


def _environment_payload() -> dict[str, Any]:
    return {
        "name": "swiss-legal-environment",
        "packages": ["python3", "qdrant-client", "lxml"],
        "network_allowlist": [
            "data.fedlex.admin.ch",
            "www.bj.admin.ch",
            "be.ch",
            "zh.ch",
            "ge.ch",
            "bger.ch",
        ],
    }


def _vault_payload() -> dict[str, Any]:
    return {
        "name": "swiss-legal-mcp-vault",
        "credentials": [],
    }


def _headers() -> dict[str, str]:
    return {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": settings.managed_agents_beta,
        "content-type": "application/json",
    }


def _persist_env(updates: dict[str, str]) -> None:
    """Write the new IDs back to backend/.env so the next boot picks them up.

    Atomic write: build the new contents in memory, then replace the
    file in one ``Path.write_text``. Existing keys are updated in place
    to preserve operator-edited ordering / comments where possible.
    """
    env_path = Path(__file__).resolve().parents[3] / ".env"
    existing: dict[str, str] = {}
    lines: list[str] = []
    if env_path.exists():
        for raw in env_path.read_text().splitlines():
            if "=" in raw and not raw.lstrip().startswith("#"):
                k, _, v = raw.partition("=")
                existing[k.strip()] = v
            lines.append(raw)
    out: list[str] = []
    seen: set[str] = set()
    for raw in lines:
        if "=" in raw and not raw.lstrip().startswith("#"):
            k = raw.split("=", 1)[0].strip()
            if k in updates:
                out.append(f"{k}={updates[k]}")
                seen.add(k)
                continue
        out.append(raw)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    env_path.write_text("\n".join(out) + "\n")
    logger.info("bootstrap_persisted_env keys=%s", sorted(updates))


def bootstrap(*, dry_run: bool = False) -> dict[str, str]:
    """Create or update the agent + environment + vault.

    Returns the resulting IDs as a dict so callers (and the CLI) can
    surface them without re-reading the .env. ``dry_run=True`` prints
    the JSON payloads instead of POSTing them — useful for code review
    before a live cluster mutation.
    """
    agent_body = _agent_payload()
    env_body = _environment_payload()
    vault_body = _vault_payload()

    if dry_run:
        print(
            json.dumps(
                {"agent": agent_body, "environment": env_body, "vault": vault_body},
                indent=2,
            )
        )
        return {}

    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is unset; bootstrap requires Anthropic credentials."
        )

    with httpx.Client(
        base_url=settings.anthropic_api_base, timeout=60.0
    ) as client:
        # Agent: create or update-by-version. We don't try to look up
        # an existing agent by name (the API doesn't expose a
        # name-search) — the .env's MANAGED_AGENT_ID is the sole
        # cross-run handle. Empty → create.
        if settings.managed_agent_id:
            r = client.put(
                f"/v1/agents/{settings.managed_agent_id}",
                json={**agent_body, "version": settings.managed_agent_version or 1},
                headers=_headers(),
            )
        else:
            r = client.post("/v1/agents", json=agent_body, headers=_headers())
        r.raise_for_status()
        agent = r.json()

        if settings.managed_environment_id:
            env = {"id": settings.managed_environment_id}
        else:
            r = client.post(
                "/v1/environments", json=env_body, headers=_headers()
            )
            r.raise_for_status()
            env = r.json()

        if settings.managed_vault_id:
            vault = {"id": settings.managed_vault_id}
        else:
            r = client.post("/v1/vaults", json=vault_body, headers=_headers())
            r.raise_for_status()
            vault = r.json()

    ids = {
        "MANAGED_AGENT_ID": str(agent["id"]),
        "MANAGED_AGENT_VERSION": str(agent.get("version", 1)),
        "MANAGED_ENVIRONMENT_ID": str(env["id"]),
        "MANAGED_VAULT_ID": str(vault["id"]),
    }
    _persist_env(ids)
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the request bodies instead of POSTing them.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        ids = bootstrap(dry_run=args.dry_run)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "bootstrap_http_error status=%d body=%s",
            exc.response.status_code,
            exc.response.text[:500],
        )
        return 2
    except Exception as exc:
        logger.error("bootstrap_failed exc=%s msg=%s", type(exc).__name__, exc)
        return 1
    if ids:
        for k, v in ids.items():
            print(f"{k}={v}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
