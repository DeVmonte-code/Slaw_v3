from __future__ import annotations

from pydantic import BaseModel, Field


class All(BaseModel):
    all: list[TriggerExpr]


class Any_(BaseModel):
    any: list[TriggerExpr]


class Not(BaseModel):
    not_: TriggerExpr = Field(alias="not")

    model_config = {"populate_by_name": True}


class Eq(BaseModel):
    eq: tuple[str, str | int | float | bool]


class Gte(BaseModel):
    gte: tuple[str, float]


class Lte(BaseModel):
    lte: tuple[str, float]


class Gt(BaseModel):
    gt: tuple[str, float]


class Lt(BaseModel):
    lt: tuple[str, float]


class In(BaseModel):
    in_: tuple[str, list[str | int | float]] = Field(alias="in")

    model_config = {"populate_by_name": True}


class Between(BaseModel):
    between: tuple[str, tuple[float, float]]


class Exists(BaseModel):
    exists: str


class EventWithinYears(BaseModel):
    event_within_years: tuple[str, int]


TriggerExpr = (
    All | Any_ | Not | Eq | Gte | Lte | Gt | Lt | In | Between | Exists | EventWithinYears
)

All.model_rebuild()
Any_.model_rebuild()
Not.model_rebuild()
