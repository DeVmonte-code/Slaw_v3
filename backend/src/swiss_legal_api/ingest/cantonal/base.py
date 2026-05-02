"""Common contract shared by every cantonal adapter.

Cantonal compilations have wildly different publishing formats, but the
downstream Qdrant pipeline only cares about a single record shape — the
same one Fedlex emits, with two extra fields:

  * ``canton`` — two-letter cantonal code (``"ZH"``, ``"BE"``, ``"GE"``).
  * ``compilation_id`` — the per-canton Systematic Compilation key
    (e.g. ``"412.31"`` for ZH-Lex 412.31, ``"A2.05"`` for Geneva RS
    A 2 05). This becomes ``sr_number`` in the seeder payload because the
    retrieval layer keys filters on ``sr_number`` regardless of source —
    the ``canton`` payload field disambiguates a cantonal "412.31" from
    a hypothetical federal one.

Adapters MUST emit deterministic output so the snapshot file is
byte-stable across re-runs (downstream UUID5 IDs depend on stable
ordering for human review).
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CantonalArticleRecord:
    """One Qdrant-bound row from a cantonal compilation.

    Mirrors :class:`swiss_legal_api.ingest.fedlex.ArticleRecord` so the
    seeder's existing payload pipeline accepts these rows unchanged
    (after the small adapter shim in :mod:`__main__` that maps
    ``compilation_id`` -> ``sr_number``).
    """

    canton: str
    compilation_id: str
    article: str
    paragraph: str
    language: str
    text: str
    source_url: str
    effective_date: str | None
    repealed_date: str | None = None

    def as_payload(self) -> dict[str, Any]:
        """Shape the seeder consumes (same columns as Fedlex rows).

        ``eli_uri`` is namespaced under ``cantonal:<canton>:<id>`` so the
        seeder's UUID5 ID derivation produces stable, collision-free IDs
        across re-runs and across cantons. The ``source_url`` is kept as
        a separate payload field for transparency / debugging — the UI
        renders it under the citation as a "view source" link.
        """
        eli_uri = f"cantonal:{self.canton}:{self.compilation_id}"
        return {
            "eli_uri": eli_uri,
            "sr_number": self.compilation_id,
            "article": self.article,
            "paragraph": self.paragraph,
            "language": self.language,
            "text": self.text,
            "canton": self.canton,
            "source_url": self.source_url,
            "effective_date": self.effective_date,
            "repealed_date": self.repealed_date,
        }


def _split_numeric(s: str) -> tuple[int, str]:
    """Numeric prefix + letter suffix — same convention as Fedlex.

    Yields ``"9" < "9a" < "10"`` so sort output matches the Fedlex
    snapshot's ordering invariant. Compilation IDs that start with a
    letter (Geneva) sort by the leading letter first, which is fine
    because adapters don't mix compilations across canton boundaries.
    """
    m = re.match(r"^(\d+)(.*)$", s)
    if not m:
        return (0, s)
    return (int(m.group(1)), m.group(2))


def sort_records(records: Iterable[CantonalArticleRecord]) -> list[CantonalArticleRecord]:
    """Deterministic sort by (canton, compilation_id, article, paragraph, language).

    Mirrors :func:`swiss_legal_api.ingest.fedlex._sort_records` so the
    cantonal snapshot file has the same sortedness guarantee.
    """

    def key(r: CantonalArticleRecord) -> tuple[Any, ...]:
        return (
            r.canton,
            r.compilation_id,
            _split_numeric(r.article),
            _split_numeric(r.paragraph),
            r.language,
        )

    return sorted(records, key=key)


def write_snapshot(
    records: Iterable[CantonalArticleRecord], path: Path
) -> int:
    """Serialise sorted records to JSON, returning the row count.

    Output shape is identical to ``law_articles.fedlex.json`` so the
    existing seeder ingests it with a single ``--source`` switch (or via
    the auto-merge logic in :func:`seed_qdrant._load_articles`).
    """
    sorted_records = sort_records(records)
    payload = [r.as_payload() for r in sorted_records]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(payload)
