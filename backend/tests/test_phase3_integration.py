"""
Phase 3 integration test — live scan of the May 5 test profile.
Requires a running Anthropic API key in environment.
Marked as integration to allow skipping in unit test runs.
"""

import asyncio
import os

import pytest

from swiss_legal_api.catalog import load_catalog
from swiss_legal_api.engine.scan import run_benefit_scan
from swiss_legal_api.schemas.context_profile import ContextProfile

# Skip if no API key present
pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — integration test skipped",
)

MAY5_TEST_PROFILE = ContextProfile(
    canton="BE",
    employment_status="student",
    employment_start_year=2018,
    weekly_hours=15,
    commute_km_daily=3,
    housing_status="tenant",
    rental_start_year=2019,
    rent_chf_monthly=730,
    lease_reference_rate_tracked=True,
    lease_type="indefinite",
    marital_status="divorced",
    household_size=3,
    children_count=0,
    has_third_pillar=True,
    third_pillar_chf_this_year=300,
    nationality_status="eu_efta",  # Non-Swiss — B permit implied
    permit_type="B",  # Set explicitly for this test
    personal_note=(
        "I am a student that works here and have to renovate the B permit every year "
        "but I want to change my legal status from student to a registered partnership"
    ),
)


SENTINEL_IDS = {
    "rent_reduction_reference_rate",
    "health_premium_reduction_ipv",
    "student_professional_training_deduction",
    "quellensteuer_correction_inferred_permit",
    "student_b_permit_renewal_right",
}


def test_may5_profile_returns_seven_or_more_benefits() -> None:
    """
    The May 5 test profile must return ≥ 7 benefits with confidence ≥ 0.6.
    Baseline before this sprint was 3 (tenancy only).
    """
    catalog = load_catalog()
    results = asyncio.run(run_benefit_scan(MAY5_TEST_PROFILE, catalog)).benefits

    passing = [r for r in results if r.confidence >= 0.6]
    benefit_ids = {r.entitlement_id for r in passing}

    # Check sentinel presence
    found = SENTINEL_IDS & benefit_ids

    assert len(passing) >= 7, f"Expected >= 7 benefits, found {len(passing)}"
    assert len(found) >= 3, f"Expected >= 3 sentinels, found {len(found)}"
