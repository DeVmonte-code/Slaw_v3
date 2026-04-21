from __future__ import annotations

from pydantic import BaseModel, Field

from .citation import Citation
from .entitlement import EstimatedValue


class EvidenceItem(BaseModel):
    field: str
    value: str | int | float | bool | None


class Benefit(BaseModel):
    entitlement_id: str
    title: str
    category: str
    estimated_value_chf: EstimatedValue
    confidence: float = Field(..., ge=0, le=1)
    citations: list[Citation] = Field(..., min_length=1)
    evidence: list[EvidenceItem]
    required_action: str
    action_template_id: str | None = None
    time_limit_days: int | None = None
    llm_reasoning: str
    disclaimer: str = (
        "Not a substitute for advice from a Swiss attorney "
        "registered with a cantonal bar."
    )


class BenefitReport(BaseModel):
    generated_at: str
    profile_hash: str
    benefits: list[Benefit]
    suppressed_count: int = Field(..., ge=0)
