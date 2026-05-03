#44 - Remove orphan SR 831.40 articles from the manual seed
What & Why
backend/seed/law_articles.json carries articles for SR 831.40 (BVG / Occupational Pensions), but no entitlement in entitlements.json actually cites SR 831.40. These records are dead weight: they consume Qdrant vectors, slow down retrieval, and make it easy to mis-attribute a citation when debugging. Either the entitlements never landed or the seed was provisional. Either way, the corpus and the catalog should be in lock-step.

Done looks like
A quick audit confirms no entitlement cites SR 831.40 (and documents any exceptions found).
If no citations exist, the SR-831.40 records are removed from law_articles.json and the next reseed produces a smaller, cleaner Qdrant collection.
If citations DO exist that I missed, this task instead documents the gap and hands off to a follow-up that adds proper Fedlex coverage for SR 831.40 (mirror of the SR 661.11 work).
Out of scope
Adding new BVG entitlements — that's a product decision, not corpus hygiene.
Removing the embedder warm-up or other unrelated cleanups.
Steps
Grep entitlements.json for "sr_number": "831.40" to confirm zero citations.
Remove SR-831.40 entries from law_articles.json and any related fixture data.
Re-run the offline test suite to confirm no test depends on the pruned articles.
Note the change in replit.md under the "Seed Data" section.
Relevant files
backend/seed/law_articles.json
backend/seed/entitlements.json
backend/tests/test_scan_mocked.py
replit.md