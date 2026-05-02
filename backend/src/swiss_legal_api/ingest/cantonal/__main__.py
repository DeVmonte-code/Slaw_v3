"""CLI entrypoint: ``python -m swiss_legal_api.ingest.cantonal``.

Drives one or more cantonal adapters and writes a deterministic
snapshot to ``backend/seed/law_articles.cantonal.json`` (or a
caller-specified path). The seeder auto-merges this file when present,
so a typical bootstrap is::

    python -m swiss_legal_api.ingest.cantonal --canton ZH,BE,GE
    python -m swiss_legal_api.seeding.seed_qdrant

By default the CLI uses each adapter's ``discover_specs()`` to walk the
canton's published catalogue index (HTML for ZH/BE, OData for GE) and
ingest every in-force act. ``--use-starter-specs`` forces the small
inline curated list — useful for smoke runs when the canton's index is
briefly unreachable, or when a contributor only wants to refresh one
act for a fix-forward.
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import bern_bsg, geneva_rs, write_snapshot, zurich_ls
from .base import CantonalArticleRecord

logger = logging.getLogger(__name__)


# Per-canton starter spec list — fallback used by ``--use-starter-specs``
# and as the seed-snapshot bootstrap when running the CLI offline (no
# network access to canton portals). One act per canton: chosen because
# each one anchors the smoke-gate cantonal entitlement and exercises the
# parser shape end-to-end.
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

ADAPTERS: dict[str, tuple[Any, Sequence[Any]]] = {
    "ZH": (zurich_ls, ZH_STARTER_SPECS),
    "BE": (bern_bsg, BE_STARTER_SPECS),
    "GE": (geneva_rs, GE_STARTER_SPECS),
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
    parser.add_argument(
        "--use-starter-specs",
        action="store_true",
        help="Skip per-canton catalogue discovery and ingest only the small "
        "curated starter spec list (one act per canton). Useful when the "
        "canton's index is unreachable.",
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
        adapter, starter_specs = ADAPTERS[canton]
        if args.use_starter_specs:
            specs: Sequence[Any] = starter_specs
            print(f"{canton}: using {len(specs)} starter spec(s) (no discovery)")
        else:
            try:
                specs = adapter.discover_specs()
                print(f"{canton}: discovered {len(specs)} in-force act(s)")
            except Exception as exc:
                # Discovery failure must not silently shrink the corpus.
                # Fall back to starter specs and surface the failure so
                # the operator knows the catalogue surface needs
                # attention.
                logger.warning(
                    "%s: discovery failed (%s) — falling back to starter specs",
                    canton, exc,
                )
                specs = starter_specs
        records = adapter.ingest(specs)
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
