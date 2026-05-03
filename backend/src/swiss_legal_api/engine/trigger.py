from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..schemas import ContextProfile
from ..schemas.trigger_dsl import (
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


@dataclass
class EvalResult:
    matched: bool
    evidence: list[dict[str, Any]] = field(default_factory=list)


def _resolve(profile: ContextProfile, path: str) -> Any:
    obj: Any = profile
    for key in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif hasattr(obj, key):
            obj = getattr(obj, key)
        else:
            return None
        if obj is None:
            return None
    return obj


def _record(path: str, profile: ContextProfile) -> dict[str, Any]:
    v = _resolve(profile, path)
    if isinstance(v, (str, int, float, bool)) or v is None:
        return {"field": path, "value": v}
    return {"field": path, "value": str(v)}


def evaluate_trigger(expr: TriggerExpr, profile: ContextProfile) -> EvalResult:
    if isinstance(expr, All):
        subs = [evaluate_trigger(e, profile) for e in expr.all]
        return EvalResult(
            matched=all(s.matched for s in subs),
            evidence=[e for s in subs for e in s.evidence],
        )
    if isinstance(expr, Any_):
        subs = [evaluate_trigger(e, profile) for e in expr.any]
        return EvalResult(
            matched=any(s.matched for s in subs),
            evidence=[e for s in subs for e in s.evidence],
        )
    if isinstance(expr, Not):
        r = evaluate_trigger(expr.not_, profile)
        return EvalResult(matched=not r.matched, evidence=r.evidence)
    if isinstance(expr, Eq):
        f, val = expr.eq
        ev = _record(f, profile)
        return EvalResult(matched=ev["value"] == val, evidence=[ev])
    if isinstance(expr, Gte):
        f, val = expr.gte
        ev = _record(f, profile)
        x = ev["value"]
        return EvalResult(matched=isinstance(x, (int, float)) and x >= val, evidence=[ev])
    if isinstance(expr, Lte):
        f, val = expr.lte
        ev = _record(f, profile)
        x = ev["value"]
        return EvalResult(matched=isinstance(x, (int, float)) and x <= val, evidence=[ev])
    if isinstance(expr, Gt):
        f, val = expr.gt
        ev = _record(f, profile)
        x = ev["value"]
        return EvalResult(matched=isinstance(x, (int, float)) and x > val, evidence=[ev])
    if isinstance(expr, Lt):
        f, val = expr.lt
        ev = _record(f, profile)
        x = ev["value"]
        return EvalResult(matched=isinstance(x, (int, float)) and x < val, evidence=[ev])
    if isinstance(expr, In):
        f, vals = expr.in_
        ev = _record(f, profile)
        return EvalResult(matched=ev["value"] in vals, evidence=[ev])
    if isinstance(expr, Between):
        f, (lo, hi) = expr.between
        ev = _record(f, profile)
        x = ev["value"]
        return EvalResult(matched=isinstance(x, (int, float)) and lo <= x <= hi, evidence=[ev])
    if isinstance(expr, Exists):
        ev = _record(expr.exists, profile)
        return EvalResult(matched=ev["value"] is not None, evidence=[ev])
    if isinstance(expr, EventWithinYears):
        name, years = expr.event_within_years
        threshold = datetime.now().year - years
        matches = [e for e in profile.recent_life_events if e.event == name and e.year >= threshold]
        ev = {"field": f"recent_life_events[{name}]", "value": len(matches)}
        return EvalResult(matched=len(matches) > 0, evidence=[ev])
    return EvalResult(matched=False)
