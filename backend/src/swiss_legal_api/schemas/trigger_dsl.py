from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag


class _StrictTrigger(BaseModel):
    """Base for trigger variants. Forbids extra fields so that payloads like
    `{"eq": [...], "gt": [...]}` fail loudly instead of silently dropping the
    unmatched operator after the discriminator picks one."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class All(_StrictTrigger):
    kind: Literal["all"] = "all"
    all: list["TriggerExpr"]


class Any_(_StrictTrigger):
    kind: Literal["any"] = "any"
    any: list["TriggerExpr"]


class Not(_StrictTrigger):
    kind: Literal["not"] = "not"
    not_: "TriggerExpr" = Field(alias="not")


class Eq(_StrictTrigger):
    kind: Literal["eq"] = "eq"
    eq: tuple[str, str | int | float | bool]


class Gte(_StrictTrigger):
    kind: Literal["gte"] = "gte"
    gte: tuple[str, float]


class Lte(_StrictTrigger):
    kind: Literal["lte"] = "lte"
    lte: tuple[str, float]


class Gt(_StrictTrigger):
    kind: Literal["gt"] = "gt"
    gt: tuple[str, float]


class Lt(_StrictTrigger):
    kind: Literal["lt"] = "lt"
    lt: tuple[str, float]


class In(_StrictTrigger):
    kind: Literal["in"] = "in"
    in_: tuple[str, list[str | int | float]] = Field(alias="in")


class Between(_StrictTrigger):
    kind: Literal["between"] = "between"
    between: tuple[str, tuple[float, float]]


class Exists(_StrictTrigger):
    kind: Literal["exists"] = "exists"
    exists: str


class EventWithinYears(_StrictTrigger):
    kind: Literal["event_within_years"] = "event_within_years"
    event_within_years: tuple[str, int]


_TRIGGER_KEYS = (
    "all",
    "any",
    "not",
    "eq",
    "gte",
    "lte",
    "gt",
    "lt",
    "in",
    "between",
    "exists",
    "event_within_years",
)


def _trigger_discriminator(v: Any) -> str | None:
    """Resolve the union tag from `kind` if present, else from the operator key.

    Lets existing JSON like `{"eq": [...]}` parse cleanly under the tagged
    union without forcing every fixture to add a redundant `kind` field, while
    still giving us O(1) discriminated-union dispatch and a stable OpenAPI tag.
    """
    if isinstance(v, dict):
        if "kind" in v:
            return str(v["kind"])
        for k in _TRIGGER_KEYS:
            if k in v:
                return k
        return None
    return getattr(v, "kind", None)


TriggerExpr = Annotated[
    Union[
        Annotated[All, Tag("all")],
        Annotated[Any_, Tag("any")],
        Annotated[Not, Tag("not")],
        Annotated[Eq, Tag("eq")],
        Annotated[Gte, Tag("gte")],
        Annotated[Lte, Tag("lte")],
        Annotated[Gt, Tag("gt")],
        Annotated[Lt, Tag("lt")],
        Annotated[In, Tag("in")],
        Annotated[Between, Tag("between")],
        Annotated[Exists, Tag("exists")],
        Annotated[EventWithinYears, Tag("event_within_years")],
    ],
    Discriminator(_trigger_discriminator),
]

All.model_rebuild()
Any_.model_rebuild()
Not.model_rebuild()
