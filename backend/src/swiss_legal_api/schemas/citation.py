from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Accepts:
#   * Federal SR numbers: "220", "642.11", "141.0".
#   * Cantonal compilation IDs encoded as letter-prefixed numbers, e.g.
#     Geneva "RS A 2 05" -> "A2.05" (spaces dropped, dot-joined). The
#     ``canton`` field disambiguates so a cantonal "412.31" never
#     collides with a federal "412.31".
SR_RE = re.compile(r"^[A-Z]*\d+(\.\d+)?$")


class Citation(BaseModel):
    sr_number: str = Field(..., description="Fedlex SR number like '220'")
    article: str = Field(..., min_length=1)
    paragraph: str | None = None
    canton: str = Field(default="CH")
    language: Literal["de", "fr", "it", "en"]
    quote_under_15_words: str
    effective_date: date | None = Field(
        default=None,
        description=(
            "Date the article entered into force (Fedlex 'Inkrafttreten'). "
            "Used to filter out not-yet-effective law at retrieval time."
        ),
    )
    repealed_date: date | None = Field(
        default=None,
        description=(
            "Date the article was repealed (Fedlex 'Aufhebung'). "
            "If null, the article is still in force."
        ),
    )
    score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Qdrant cosine similarity of the chunk that supports this "
            "citation. Set on best_citation in BenefitReport, not on seed "
            "Citations."
        ),
    )

    @field_validator("sr_number")
    @classmethod
    def _sr(cls, v: str) -> str:
        if not SR_RE.match(v):
            raise ValueError(
                "sr_number must match ^[A-Z]*\\d+(\\.\\d+)?$ "
                "(federal SR or letter-prefixed cantonal compilation ID)"
            )
        return v

    @field_validator("quote_under_15_words")
    @classmethod
    def _quote(cls, v: str) -> str:
        if len(v.strip().split()) > 15:
            raise ValueError("quote must be 15 words or fewer")
        return v
