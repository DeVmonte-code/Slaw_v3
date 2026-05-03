#42 - Bootstrap the Fedlex law snapshot file
What & Why
Task #19 shipped swiss_legal_api/ingest/fedlex.py (a working SPARQL + Akoma Ntoso ingester) and seed_qdrant.py already knows how to merge a seed/law_articles.fedlex.json snapshot with the manual law_articles.json fallback. But the snapshot file has never actually been generated — the ingester CLI has never been run on this environment, so today Qdrant is seeded only from the 36 hand-pasted articles. That means every benefit that cites a law article missing from the manual file fails retrieval silently.

This task closes the gap by running the existing ingester end-to-end and checking the snapshot into the seed directory so subsequent reseeds use authoritative Fedlex text.

Done looks like
backend/seed/law_articles.fedlex.json exists, is sorted deterministically, and contains DE (and where available FR/IT) text for every SR cited by the entitlement catalog: 141.0, 142.20, 220, 642.11, 661.11, 837.0.
The ingester run prints a summary line of the form "ingested N articles across 6 SRs in K languages" and exits 0.
A diff against the existing manual law_articles.json shows the new file covers every (sr_number, article) pair currently used by the manual seed, so the merge logic in seed_qdrant.py can prefer Fedlex.
The snapshot is reproducible: re-running the CLI on the same day produces a byte-identical file.
Out of scope
Running seed_qdrant.py against the new file — that's the next task.
English translations (Fedlex doesn't publish them; keep the curated EN records in the manual seed for now).
Cantonal articles (separate law_articles.cantonal.json pipeline).
Any change to the ingester logic itself — just running it.
Steps
Invoke the existing ingester CLI for all 6 cited SR numbers and write the output to the canonical seed path.
Eyeball-validate by spot-checking 2-3 known articles (e.g. CO Art. 270a, AVIG Art. 8) against the published Fedlex text.
Confirm the file is sorted by (sr_number, article, paragraph, language) so future diffs are reviewable.
Commit the snapshot to the repo so the next person doesn't have to re-run the network-dependent ingester just to bring up a dev env.
Relevant files
backend/src/swiss_legal_api/ingest/fedlex.py
backend/src/swiss_legal_api/seeding/seed_qdrant.py:117-184
backend/seed/law_articles.json
backend/seed/entitlements.json