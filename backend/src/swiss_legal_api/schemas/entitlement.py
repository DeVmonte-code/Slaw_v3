from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .citation import Citation
from .trigger_dsl import TriggerExpr


class TitleI18n(BaseModel):
    de: str
    fr: str | None = None
    it: str | None = None
    en: str


Category = Literal[
    "tax_deduction", "tenancy_right", "employment_right", "family_benefit",
    "business_subsidy", "social_security", "consumer_protection",
]
RequiredAction = Literal[
    "claim_letter_to_landlord", "tax_declaration_field", "employer_request",
    "cantonal_application", "federal_application", "consultation_with_lawyer",
]
ValuePer = Literal["year", "one_time", "month"]


class EstimatedValue(BaseModel):
    min: float = Field(..., ge=0)
    max: float = Field(..., ge=0)
    per: ValuePer = "year"


class Entitlement(BaseModel):
    id: str = Field(..., min_length=1)
    title: TitleI18n
    category: Category
    jurisdiction: str = Field(..., min_length=2)
    source_citations: list[Citation] = Field(..., min_length=1)
    trigger: TriggerExpr
    estimated_value_chf: EstimatedValue
    required_action: RequiredAction
    action_template_id: str | None = None
    time_limit_days: int | None = None
    confidence_floor: float = Field(default=0.6, ge=0, le=1)
