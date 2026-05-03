"""Catalog → schema field-path validator.

Walks every trigger expression in `seed/entitlements.json`, extracts the
field paths referenced by leaf operators, and verifies that each top-level
field exists on `ContextProfile`. Also checks that any `event_within_years`
event name is a valid `LifeEventKind`.

Exits non-zero on any mismatch so it can be wired into smoke / CI as a
hard gate. Run from `backend/`:

    python scripts/validate_catalog.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import get_args

# Make `src/` importable when this file is executed as a plain script
# (`python scripts/validate_catalog.py`). pytest already does this via
# `pythonpath = ["src"]` in pyproject.toml, but standalone runs don't.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_ROOT / "src"))

from swiss_legal_api.schemas import ContextProfile, Entitlement
from swiss_legal_api.schemas.context_profile import LifeEventKind
from swiss_legal_api.schemas.trigger_dsl import (
    All,
    Any_,
    Between,
    Eq,
    EventWithinYears,
    Exists,
    Gt,
    Gte,
    In,
    Lt,
    Lte,
    Not,
    TriggerExpr,
)


def _collect(expr: TriggerExpr) -> list[tuple[str, str | None]]:
    """Return (field_path, life_event_name_or_None) tuples for every leaf."""
    if isinstance(expr, All):
        return [p for sub in expr.all for p in _collect(sub)]
    if isinstance(expr, Any_):
        return [p for sub in expr.any for p in _collect(sub)]
    if isinstance(expr, Not):
        return _collect(expr.not_)
    if isinstance(expr, Eq):
        return [(expr.eq[0], None)]
    if isinstance(expr, Gte):
        return [(expr.gte[0], None)]
    if isinstance(expr, Lte):
        return [(expr.lte[0], None)]
    if isinstance(expr, Gt):
        return [(expr.gt[0], None)]
    if isinstance(expr, Lt):
        return [(expr.lt[0], None)]
    if isinstance(expr, In):
        return [(expr.in_[0], None)]
    if isinstance(expr, Between):
        return [(expr.between[0], None)]
    if isinstance(expr, Exists):
        return [(expr.exists, None)]
    if isinstance(expr, EventWithinYears):
        # First element is the LifeEventKind, not a profile field path.
        # The actual profile attribute walked at runtime is recent_life_events.
        return [("recent_life_events", expr.event_within_years[0])]
    return []


def main() -> int:
    seed_path = Path(__file__).resolve().parents[1] / "seed" / "entitlements.json"
    data = json.loads(seed_path.read_text())

    profile_fields = set(ContextProfile.model_fields.keys())
    valid_event_kinds = set(get_args(LifeEventKind))

    errors: list[str] = []

    for row in data:
        try:
            e = Entitlement.model_validate(row)
        except Exception as exc:
            # Catch-all is intentional: surface every parse failure across the
            # whole catalog rather than aborting on the first bad row.
            errors.append(f"{row.get('id', '?')}: failed to parse entitlement: {exc}")
            continue
        for field, event in _collect(e.trigger):
            top = field.split(".")[0]
            if top not in profile_fields:
                errors.append(
                    f"{e.id}: trigger references unknown field '{field}' "
                    f"(top-level '{top}' not in ContextProfile.model_fields)"
                )
            if event is not None and event not in valid_event_kinds:
                errors.append(
                    f"{e.id}: event_within_years uses unknown event kind '{event}' "
                    f"(not a valid LifeEventKind)"
                )

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(
        f"OK: validated {len(data)} entitlements, all trigger field paths exist on ContextProfile."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
