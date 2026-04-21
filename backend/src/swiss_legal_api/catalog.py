from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .schemas import Entitlement


@lru_cache(maxsize=1)
def load_catalog() -> list[Entitlement]:
    path = Path(__file__).resolve().parents[2] / "seed" / "entitlements.json"
    data = json.loads(path.read_text())
    return [Entitlement.model_validate(row) for row in data]
