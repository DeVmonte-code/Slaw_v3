"""Deterministic trigger invariants for the permit-status sprint.

Loads each persona fixture and asserts that the trigger evaluation phase
(before Claude verification) selects the expected set of entitlements for
that permit + nationality combination. Catches catalog regressions without
needing live Anthropic / Qdrant access.
"""

from __future__ import annotations

import json
from pathlib import Path

from swiss_legal_api.catalog import load_catalog
from swiss_legal_api.engine.trigger import evaluate_trigger
from swiss_legal_api.schemas import ContextProfile

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load(name: str) -> ContextProfile:
    return ContextProfile.model_validate(json.loads((FIXTURES / name).read_text()))


def _triggered_ids(profile: ContextProfile) -> set[str]:
    catalog = load_catalog()
    return {e.id for e in catalog if evaluate_trigger(e.trigger, profile).matched}


def test_luis_swiss_skips_permit_only_entitlements() -> None:
    ids = _triggered_ids(_load("luis_profile.json"))
    # Permit-only entitlements never apply to Swiss citizens.
    assert "quellensteuer_subsequent_assessment" not in ids
    assert "naturalisation_eligibility" not in ids
    assert "family_reunification_right" not in ids
    # Pre-sprint regression baseline: Luis still picks up his usual benefits.
    assert "childcare_cost_deduction" in ids
    assert "rent_reduction_reference_rate" in ids
    assert "third_pillar_deduction" in ids


def test_b_permit_eu_employee_triggers_quellensteuer_only() -> None:
    ids = _triggered_ids(_load("b_permit_eu_employee.json"))
    assert "quellensteuer_subsequent_assessment" in ids
    # B-permit holder with <10 yrs cannot naturalise.
    assert "naturalisation_eligibility" not in ids
    # Single, no kids → nothing to reunify.
    assert "family_reunification_right" not in ids
    # No kids → childcare deduction stays off.
    assert "childcare_cost_deduction" not in ids


def test_c_permit_third_country_triggers_full_permit_set() -> None:
    ids = _triggered_ids(_load("c_permit_third_country.json"))
    assert "naturalisation_eligibility" in ids
    assert "family_reunification_right" in ids
    assert "childcare_cost_deduction" in ids
    # C-permit holders are no longer Quellensteuer-subject.
    assert "quellensteuer_subsequent_assessment" not in ids


def test_unemployment_requires_swiss_or_residency_permit() -> None:
    """P4 retrofit: unemployment_insurance gated by nationality / permit."""
    catalog = load_catalog()
    unemp = next(e for e in catalog if e.id == "unemployment_insurance_entitlement")

    swiss_unemployed = ContextProfile.model_validate(
        {
            "canton": "ZH",
            "employment_status": "unemployed",
            "housing_status": "tenant",
            "marital_status": "single",
            "income_band_chf": "lt_30k",
            "nationality_status": "swiss",
            "permit_type": "none",
        }
    )
    assert evaluate_trigger(unemp.trigger, swiss_unemployed).matched is True

    no_permit_unemployed = ContextProfile.model_validate(
        {
            "canton": "ZH",
            "employment_status": "unemployed",
            "housing_status": "tenant",
            "marital_status": "single",
            "income_band_chf": "lt_30k",
            "nationality_status": "third_country",
            "permit_type": "none",
        }
    )
    assert evaluate_trigger(unemp.trigger, no_permit_unemployed).matched is False

    b_permit_unemployed = ContextProfile.model_validate(
        {
            "canton": "VD",
            "employment_status": "unemployed",
            "housing_status": "tenant",
            "marital_status": "single",
            "income_band_chf": "lt_30k",
            "nationality_status": "eu_efta",
            "permit_type": "B",
        }
    )
    assert evaluate_trigger(unemp.trigger, b_permit_unemployed).matched is True


def test_naturalisation_unknown_years_does_not_match() -> None:
    """years_in_switzerland=None must not satisfy the gte threshold."""
    catalog = load_catalog()
    nat = next(e for e in catalog if e.id == "naturalisation_eligibility")
    profile = ContextProfile.model_validate(
        {
            "canton": "ZH",
            "employment_status": "employee_full_time",
            "housing_status": "tenant",
            "marital_status": "single",
            "income_band_chf": "80_120k",
            "nationality_status": "third_country",
            "permit_type": "C",
            # years_in_switzerland deliberately omitted → defaults to None
        }
    )
    assert evaluate_trigger(nat.trigger, profile).matched is False
