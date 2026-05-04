#49 - Acceptance gate: 100% agent-backed verifications
What & Why
The previous two tasks fix the immediate gap, but nothing prevents a future config drift, a partial outage, or a code change from silently sliding the system back to one-shot messages.create calls. The /admin/audits/agent-backed endpoint already aggregates per-verification provenance — this task turns it into an enforced gate so a regression surfaces as a failed check, not as a quiet quality drop.

Done looks like
A scripts/check_agent_backed.sh (or Python equivalent) runs one canonical Luis profile scan, then queries /admin/audits/agent-backed?since=<scan_start_iso> and exits non-zero unless agent_backed_pct == 100.0 and `total_benefits
= 5`.

The smoke gate (backend/scripts/smoke.sh) calls this checker after the existing benefit-count assertion, so any deploy that loses the agent posture fails the smoke gate before reaching users.
A scheduled job (or a one-line addition to the existing nightly sweep) writes agent_backed_pct to a small metrics line so a long-term drift is observable, not just a single point-in-time check.
An entry in backend/README.md documents the gate, its threshold, and how to investigate when it fails (drill into ?details=true&job_id=... to find the exact verifications that fell back).
A unit test in backend/tests/test_admin_audits.py exercises the endpoint with a fixture that mixes agent-backed and fallback records and asserts the percentage math is correct.
Out of scope
Building a UI for the gate — CLI / log line is sufficient.
Paging / alerting infrastructure beyond a structured log line.
Replacing the existing smoke gate; this extends it.
Steps
Add the post-scan checker that hits /admin/audits/agent-backed with the right since window and asserts the threshold.
Wire the checker into scripts/smoke.sh after the verified- benefit count assertion.
Add the nightly metrics line to the scheduler so long-term agent_backed_pct is logged.
Add the percentage-math unit test with mixed-provenance fixtures.
Document the gate, its threshold, and the drill-down recipe.
Relevant files
backend/src/swiss_legal_api/api/main.py:823-880
backend/src/swiss_legal_api/engine/audit.py
backend/src/swiss_legal_api/scheduler.py
backend/scripts/smoke.sh
backend/tests/test_admin_audits.py
backend/README.md
Dependencies
Wire managed-agent IDs into runtime and flip the flag