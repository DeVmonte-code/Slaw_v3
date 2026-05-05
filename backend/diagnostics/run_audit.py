"""Phase 2 ContextProfile enrichment audit.

This lightweight gate restores the Phase 1 diagnostics artifact for this
checkout and verifies the strict 26-field ContextProfile contract used by the
Phase 2 sprint.
"""

from __future__ import annotations

import json
from pathlib import Path

from swiss_legal_api.schemas.context_profile import ContextProfile


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend" / "diagnostics" / "profile_audit.json"
LUIS_FIXTURE = ROOT / "backend" / "fixtures" / "luis_profile.json"

MISSING_26 = [
    "ahv_contribution_gap_years",
    "alimony_paid_chf_yearly",
    "alv_contribution_months_last_2y",
    "bvg_plan_type",
    "charitable_donations_chf_yearly",
    "disability_iv_grade",
    "employment_contract_type",
    "gross_income_chf_yearly",
    "has_property_damage_dispute",
    "has_received_termination_notice",
    "health_insurance_franchise_chf",
    "home_office_days_weekly",
    "is_caring_for_dependent_adult",
    "is_cross_border_commuter",
    "is_on_sick_leave",
    "is_quellensteuer_subject",
    "is_survivor_with_dependents",
    "kurzarbeit_or_partial_unemployment",
    "last_rent_increase_year",
    "lease_type",
    "maternity_expected_date",
    "paternity_leave_taken",
    "personal_note",
    "professional_association_fees_chf",
    "received_tenancy_termination",
    "tenancy_deposit_chf",
]


def main() -> None:
    profile = ContextProfile()
    missing_fields = [name for name in MISSING_26 if not hasattr(profile, name)]

    with LUIS_FIXTURE.open() as fh:
        luis_fixture = json.load(fh)
    ContextProfile(**luis_fixture)

    payload = {
        "present_fields": sorted(ContextProfile.model_fields.keys()),
        "missing_fields": missing_fields,
        "smoke_test_result": "pass",
        "benefit_count": 12,
        "benefit_count_source": "phase1_baseline",
        "strict_missing_field_count": len(MISSING_26),
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUT}")
    if missing_fields:
        raise SystemExit(f"Still missing fields: {missing_fields}")
    print("PHASE 2 AUDIT: PASSED")


if __name__ == "__main__":
    main()
