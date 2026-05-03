"""Cantonal-law ingestion adapters.

Each canton publishes its Systematic Compilation differently — there is no
unified SPARQL endpoint analogous to Fedlex — so every canton gets its own
adapter under this package. Adapters all return the same shape
(:class:`base.CantonalArticleRecord`) so the CLI and seeder don't need to
care about the source.

Currently wired:
  * :mod:`zurich_ls`   — Zurich, ZH-Lex (HTML).
  * :mod:`bern_bsg`    — Bern, BSG / Belex (HTML; PDF fallback documented).
  * :mod:`geneva_rs`   — Geneva, RSG (HTML; OData feed shape documented).

Adding a new canton: drop ``<canton_short>_<compilation>.py`` here, expose
a ``CANTON``, ``COMPILATION_LABEL`` and ``ingest()`` symbol with the same
signature as the existing adapters, and add it to ``ADAPTERS`` in
:mod:`__main__`.
"""

from __future__ import annotations

from .base import (
    CantonalArticleRecord,
    write_snapshot,
)

__all__ = [
    "CantonalArticleRecord",
    "write_snapshot",
]
