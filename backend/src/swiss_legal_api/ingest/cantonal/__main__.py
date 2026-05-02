"""CLI entrypoint: ``python -m swiss_legal_api.ingest.cantonal``.

Drives one or more cantonal adapters and writes a deterministic
snapshot to ``backend/seed/law_articles.cantonal.json`` (or a
caller-specified path). The seeder auto-merges this file when present,
so a typical bootstrap is::

    python -m swiss_legal_api.ingest.cantonal --canton ZH,BE,GE
    python -m swiss_legal_api.seeding.seed_qdrant

The starter spec list per canton is intentionally tiny — one act per
canton chosen to exercise the parser and ship one end-to-end smoke
entitlement. Contributors extend the list as new entitlements need new
acts; nothing about the framework requires the spec list to be inline
forever (a follow-up will move it to a YAML manifest under
``seed/cantonal/``).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import bern_bsg, geneva_rs, write_snapshot, zurich_ls
from .base import CantonalArticleRecord

logger = logging.getLogger(__name__)


# Per-canton starter spec list. URLs are the published act pages on each
# cantonal portal; the adapter fetches the HTML and parses in-process.
# Effective dates are the act's promulgation date so the retrieval
# filter's "effective_date <= today" gate passes for current scans.
ZH_STARTER_SPECS = [
    zurich_ls.ArticleSpec(
        url="https://www.zhlex.zh.ch/Erlass.html?Open&Ordnr=412.31",
        compilation_id="412.31",  # Volksschulgesetz
        language="de",
        effective_date="2005-08-22",
    ),
]
BE_STARTER_SPECS = [
    bern_bsg.ArticleSpec(
        url="https://www.belex.sites.be.ch/data/661.11/de",
        compilation_id="661.11",  # Mietverfahrensverordnung
        language="de",
        effective_date="1996-01-01",
    ),
]
GE_STARTER_SPECS = [
    geneva_rs.ArticleSpec(
        url="https://www.lexfind.ch/fe/fr/tol/24891/fr",
        compilation_id="A 2 05",  # Constitution genevoise
        language="fr",
        effective_date="2013-06-01",
    ),
]

ADAPTERS: dict[str, tuple[object, list[object]]] = {
    "ZH": (zurich_ls, list(ZH_STARTER_SPECS)),
    "BE": (bern_bsg, list(BE_STARTER_SPECS)),
    "GE": (geneva_rs, list(GE_STARTER_SPECS)),
}


def _split_csv(raw: str) -> list[str]:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m swiss_legal_api.ingest.cantonal",
        description="Ingest cantonal-law articles from the per-canton "
        "Systematic Compilations.",
    )
    parser.add_argument(
        "--canton",
        default="ZH,BE,GE",
        help="Comma-separated canton codes (default: ZH,BE,GE — the three "
        "currently-wired adapters).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output path (default: backend/seed/law_articles.cantonal.json).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    cantons = _split_csv(args.canton)
    unknown = [c for c in cantons if c not in ADAPTERS]
    if unknown:
        print(
            f"Unknown canton(s): {', '.join(unknown)}. "
            f"Available: {', '.join(sorted(ADAPTERS))}",
            file=sys.stderr,
        )
        return 1

    out_path = (
        Path(args.out)
        if args.out
        else Path(__file__).resolve().parents[4] / "seed" / "law_articles.cantonal.json"
    )

    all_records: list[CantonalArticleRecord] = []
    for canton in cantons:
        adapter, specs = ADAPTERS[canton]
        # `adapter.ingest` is the per-canton driver — duck-typed via the
        # CantonalAdapter Protocol in `base.py`. The module reference is
        # an `object` at the type level (see ADAPTERS) but is always a
        # module exposing `ingest()` at runtime.
        records = adapter.ingest(specs)  # type: ignore[attr-defined]
        print(
            f"{canton}: ingested {len(records)} paragraphs "
            f"across {len({(r.compilation_id, r.article) for r in records})} "
            f"articles"
        )
        all_records.extend(records)

    n = write_snapshot(all_records, out_path)
    print(f"Wrote {n} cantonal records -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
