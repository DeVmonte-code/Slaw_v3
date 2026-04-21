from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SR_RE = re.compile(r"^\d+(\.\d+)?$")


class Citation(BaseModel):
    sr_number: str = Field(..., description="Fedlex SR number like '220'")
    article: str = Field(..., min_length=1)
    paragraph: str | None = None
    canton: str = Field(default="CH")
    language: Literal["de", "fr", "it", "en"]
    quote_under_15_words: str

    @field_validator("sr_number")
    @classmethod
    def _sr(cls, v: str) -> str:
        if not SR_RE.match(v):
            raise ValueError("sr_number must match ^\\d+(\\.\\d+)?$")
        return v

    @field_validator("quote_under_15_words")
    @classmethod
    def _quote(cls, v: str) -> str:
        if len(v.strip().split()) > 15:
            raise ValueError("quote must be 15 words or fewer")
        return v
