# Managed Agents Configuration

This document specifies the provisioning and runtime configuration of the Anthropic Managed Agents for the Slaw v3 verification engine.

## Agent Identities (Anthropic Console)

The application uses two separate Managed Agents so developmental testing does not pollute the production retrieval metrics, and so a tool bump doesn't break production.

*   **Development Agent:** `slaw-verify-dev`
*   **Production Agent:** `slaw-verify-prod`

## System Prompt

The system prompt for both agents MUST exactly match the `SYSTEM` constant declared in `backend/src/swiss_legal_api/engine/verify.py`. If you update the prompt in code, you MUST bump the agent version in the Anthropic console to match.

## Bound MCP Servers & Tools

Both agents must mount the current backend's MCP servers:
*   `swiss-law-retrieval-mcp`
*   `swiss-contract-tools-mcp`

**Tool Allow-List (Strict Read-Only):**
The agent is restricted to read-only retrieval functions. Do **NOT** grant any write/delete capabilities.
*   `fetch_article_by_sr`
*   `verify_entitlement`

## Version Bumps

When the system prompt or backend tool schema changes:
1. Navigate to the Anthropic Managed Agents console.
2. Edit the agent's system prompt or tool bindings.
3. Save the new version.
4. Note the new Version number.
5. Update the `MANAGED_AGENT_VERSION_DEV` (or `PROD`) secret in the environment/deployment definitions so the runtime targets the new specific immutable version.

## Runtime Loading

At boot, the backend reads these exact secrets. If they are missing, it defaults `use_managed_agents=False` and warns loudly in the logs (`agent_runner_unconfigured`). If they are present, it auto-enables the agentic code path (`sessions.events`) and emits `agent_runner_ready`.
