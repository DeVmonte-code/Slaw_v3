#48 - Wire managed-agent IDs into runtime and flip the flag
What & Why
With the agent provisioned and its IDs captured, the running uvicorn process still needs to actually use them. Right now the live process has USE_MANAGED_AGENTS=0 baked into its environment and managed_agent_id="" / managed_agent_version=0 defaults, so the if settings.use_managed_agents: branch in engine/verify.py:138 is never taken. This task wires the secrets through, switches the default posture, and protects the system from silent regression to one-shot calls.

Done looks like
The dev workflow reads MANAGED_AGENT_ID_DEV and MANAGED_AGENT_VERSION_DEV from secrets and exposes them to uvicorn as MANAGED_AGENT_ID / MANAGED_AGENT_VERSION. Same pattern for prod.
USE_MANAGED_AGENTS defaults to 1 whenever the IDs are present, and to 0 (with a clear startup warning) when they are missing — no silent fallback to messages.create in a configured environment.
A boot-time guard in api/main.py logs a single agent_runner_ready agent_id=... version=... line on startup so ops can see at a glance which agent the process is bound to.
start.sh does NOT export USE_MANAGED_AGENTS=0 (the lesson from Task #39 stands — env wins).
After a workflow restart, a fresh scan emits claude_call ... call_kind=sessions.events agent_backed=true tool_use_count>=1 mcp_servers_invoked=swiss-law-retrieval-mcp,... for every verification.
Out of scope
Provisioning the managed agent (covered by the previous task).
Acceptance gating in CI (covered by the next task).
New MCP servers / new tools.
Steps
Read the agent-id / agent-version secrets at process start in config.py and surface them on the Settings object.
Default use_managed_agents to True when both IDs are non-empty; keep the env override path for tests.
Add the startup agent_runner_ready log line and a agent_runner_unconfigured warning when the flag is on but IDs are missing.
Restart the workflow and confirm one fresh scan produces eight agent_backed=true log lines instead of agent_backed=false.
Relevant files
backend/src/swiss_legal_api/config.py:60-95
backend/src/swiss_legal_api/engine/verify.py:130-170
backend/src/swiss_legal_api/engine/agent_runner.py:100-160
backend/src/swiss_legal_api/api/main.py:1-80
start.sh
Dependencies
Provision the managed agent and capture its IDs