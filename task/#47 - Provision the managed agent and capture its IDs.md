#47 - Provision the managed agent and capture its IDs
What & Why
Today every scan in this environment falls back to a one-shot messages.create call because USE_MANAGED_AGENTS=0 and no MANAGED_AGENT_ID / MANAGED_AGENT_VERSION are configured. Even though engine/agent_runner.py is fully implemented and the two MCP servers (swiss-law-retrieval-mcp, swiss-contract-tools-mcp) mount cleanly at boot, the verification path can't reach them because the agent identity doesn't exist yet.

This task creates the managed agent in the Anthropic console with the right system prompt + MCP server bindings + tool allow-list, and records the resulting agent_id / version so the runtime can target it.

Done looks like
A managed agent named slaw-verify-prod (and a separate slaw-verify-dev) exists in the Anthropic console, bound to the two MCP servers the backend already mounts.
Its system prompt mirrors engine/verify.py's SYSTEM constant so behaviour parity is preserved on day one.
Its allowed tools include at minimum fetch_article_by_sr and verify_entitlement (the two the runner depends on), and nothing that would let it write or delete data.
The MANAGED_AGENT_ID and MANAGED_AGENT_VERSION for both the dev and prod agents are recorded as project secrets — never in start.sh, never in committed files.
A short docs/managed-agents.md (or section in backend/README.md) documents the agent name, its MCP bindings, the tool allow-list, and the procedure for bumping the version.
Out of scope
Flipping the runtime flag or restarting the workflow (next task).
Building new MCP servers (existing ones are sufficient).
Production rollout / deployment changes (separate task).
Any code change beyond docs.
Steps
In the Anthropic console, create the dev and prod agents with the system prompt copied verbatim from engine/verify.py.
Bind both MCP servers to each agent and restrict tool use to the read-only allow-list above.
Record the resulting agent IDs and version numbers as project secrets (MANAGED_AGENT_ID_DEV, MANAGED_AGENT_ID_PROD, plus their _VERSION siblings).
Write the operator doc covering naming, tool allow-list, and the version-bump procedure.
Relevant files
backend/src/swiss_legal_api/engine/agent_runner.py:100-170,351-470
backend/src/swiss_legal_api/engine/verify.py:40-90
backend/src/swiss_legal_api/config.py:69-90
backend/README.md