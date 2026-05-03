#46 - Nightly Fedlex refresh feeding the sweep alerts
What & Why
The sweep engine (engine/sweep.py:fedlex_changed_articles) already knows how to diff two snapshots of law_articles.fedlex.json and emit UPDATED alerts when a user's cited articles change upstream — but nothing currently produces a fresh snapshot on a schedule. So even though the diff path is live, every diff is a no-op. This task wires the ingester into the nightly scheduler so the alert path actually fires when Fedlex amends a law a user depends on.

Done looks like
A scheduled job (gated by an env var like FEDLEX_REFRESH_ENABLED=1, off by default for local dev) runs the ingester once per night, writes the new snapshot to a versioned path, and promotes it via the existing promote_fedlex_snapshot helper.
When a real upstream change is simulated (e.g. by hand-editing a test snapshot), sweep_all_users produces an UPDATED alert visible in /users/{id}/alerts for any user whose latest scan cited the affected article.
Network failures in the ingester degrade gracefully: the previous snapshot is preserved, the scheduler logs a warning, and no alert storm is triggered by a transient outage.
A short README section under "Scheduled benefit sweep" documents the new env var, the schedule, and how to disable the refresh.
Out of scope
Cantonal law scrapers (covered by Task #21, MERGED).
Re-architecting the scheduler (just adding one job).
A UI to trigger manual refreshes.
Production deploy / cron infra changes — APScheduler in-process is fine for now.
Steps
Add a scheduled job in scheduler.py that invokes the ingester for the configured SR list and writes to a timestamped path under backend/seed/snapshots/.
Promote the new snapshot via engine/sweep.py:promote_fedlex_snapshot so the next sweep run sees it as "current".
Wrap the network call in a try/except that preserves the previous snapshot on failure and logs a structured warning.
Add an integration test that drops a fixture snapshot, runs sweep_all_users, and asserts an UPDATED alert lands in the storage layer for the affected user.
Document the env var, schedule, and failure semantics.
Relevant files
backend/src/swiss_legal_api/scheduler.py
backend/src/swiss_legal_api/engine/sweep.py:270-400
backend/src/swiss_legal_api/ingest/fedlex.py
backend/src/swiss_legal_api/storage.py
backend/tests/test_sweep.py
backend/README.md
Dependencies
Reseed Qdrant from the new corpus and prove the smoke gate still holds