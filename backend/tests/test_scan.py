import json
import os
from pathlib import Path

import pytest

from swiss_legal_api.catalog import load_catalog
from swiss_legal_api.engine.scan import run_benefit_scan
from swiss_legal_api.schemas import ContextProfile

pytestmark = pytest.mark.skipif(
    not (os.getenv("ANTHROPIC_API_KEY") and os.getenv("QDRANT_URL")),
    reason="requires ANTHROPIC_API_KEY and QDRANT_URL",
)


async def test_luis_profile_returns_required_benefits():
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "luis_profile.json"
    profile = ContextProfile.model_validate(json.loads(fixture.read_text()))
    report = await run_benefit_scan(profile, load_catalog())
    assert len(report.benefits) >= 5
    ids = {b.entitlement_id for b in report.benefits}
    assert "rent_reduction_reference_rate" in ids
    assert "childcare_cost_deduction" in ids
