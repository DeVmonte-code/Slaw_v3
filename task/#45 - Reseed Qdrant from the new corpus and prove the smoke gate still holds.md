#45 - Reseed Qdrant from the new corpus and prove the smoke gate still holds
What & Why
Once the Fedlex snapshot exists, SR 661.11 is added, and SR 831.40 orphans are pruned, Qdrant must be reseeded so the merged corpus is actually retrievable at scan time. The seeder's merge logic (law_articles.fedlex.json wins, manual fills the gaps) only matters if we run it and verify the result. Without this gate, the first three tasks ship invisible improvements.

Done looks like
A clean python -m swiss_legal_api.seeding.seed_qdrant run completes without errors and reports the new article + chunk counts.
GET /readyz?deep=1 returns {"ok": true, "qdrant": "reachable", "collection": ...} with a point count > 36 (proof Fedlex content landed).
The canonical Luis smoke profile (ZH tenant + employee, married, two children) returns ≥5 verified benefits, including rent_reduction_reference_rate and childcare_cost_deduction.
A 661.11-triggering profile returns a verified benefit citing 661.11.
A short note is added under "Seed Data" in replit.md explaining that the Fedlex snapshot is now the source of truth and the manual file is fallback-only.
Out of scope
Restructuring the seeder — only run it.
Adding new entitlements.
Changing the embedder model or score threshold.
Steps
Run the seeder against the live Qdrant Cloud cluster, capturing stdout for the audit log.
Hit /readyz?deep=1 and /scan against two fixture profiles (Luis canonical + a 661.11 trigger) and record the results.
Compare verified-benefit counts and best-citation effective_date values before/after to confirm no regression.
Update replit.md to reflect the new corpus state.
Relevant files
backend/src/swiss_legal_api/seeding/seed_qdrant.py
backend/src/swiss_legal_api/api/main.py:433-500
backend/scripts/smoke.sh
replit.md
Dependencies
Remove orphan SR 831.40 articles from the manual seed
Add SR 661.11 to the legal corpus
Bootstrap the Fedlex law snapshot file