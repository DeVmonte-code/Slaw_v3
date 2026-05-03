from datetime import datetime

import pytest

from swiss_legal_api.engine.trigger import evaluate_trigger
from swiss_legal_api.schemas import ContextProfile
from swiss_legal_api.schemas.trigger_dsl import (
    All,
    Between,
    Eq,
    EventWithinYears,
    In,
    Not,
)


@pytest.fixture
def luis() -> ContextProfile:
    return ContextProfile.model_validate(
        {
            "canton": "ZH",
            "employment_status": "employee_full_time",
            "employment_start_year": 2018,
            "weekly_hours": 42,
            "housing_status": "tenant",
            "rental_start_year": 2018,
            "lease_reference_rate_tracked": True,
            "rent_chf_monthly": 2400,
            "household_size": 4,
            "children_count": 2,
            "children_ages": [3, 6],
            "marital_status": "married",
            "income_band_chf": "120_200k",
            "has_third_pillar": True,
            "third_pillar_chf_this_year": 7056,
            "commute_km_daily": 12,
            "childcare_cost_chf_yearly": 18000,
        }
    )


def test_rent_reduction_trigger_matches(luis: ContextProfile):
    expr = All.model_validate(
        {
            "all": [
                {"eq": ["housing_status", "tenant"]},
                {"lte": ["rental_start_year", 2022]},
                {"eq": ["lease_reference_rate_tracked", True]},
            ]
        }
    )
    r = evaluate_trigger(expr, luis)
    assert r.matched is True
    assert len(r.evidence) == 3


def test_childcare_trigger_matches(luis: ContextProfile):
    expr = All.model_validate(
        {
            "all": [
                {"gte": ["children_count", 1]},
                {"gte": ["childcare_cost_chf_yearly", 1]},
            ]
        }
    )
    assert evaluate_trigger(expr, luis).matched is True


def test_unemployment_trigger_false_for_employed(luis: ContextProfile):
    expr = Eq.model_validate({"eq": ["employment_status", "unemployed"]})
    assert evaluate_trigger(expr, luis).matched is False


def test_in_trigger(luis: ContextProfile):
    expr = In.model_validate({"in": ["employment_status", ["employee_full_time", "self_employed"]]})
    assert evaluate_trigger(expr, luis).matched is True


def test_not_trigger_false_when_condition_true(luis: ContextProfile) -> None:
    # Luis is a tenant — Not(tenant) should be False
    expr = Not.model_validate({"not": {"eq": ["housing_status", "tenant"]}})
    assert evaluate_trigger(expr, luis).matched is False


def test_not_trigger_true_when_condition_false(luis: ContextProfile) -> None:
    # Luis is not an owner — Not(owner) should be True
    expr = Not.model_validate({"not": {"eq": ["housing_status", "owner"]}})
    assert evaluate_trigger(expr, luis).matched is True


def test_nested_all_any_trigger(luis: ContextProfile) -> None:
    # All([Any([is_owner=False, is_married=True]), children_count>=1]) → True
    expr = All.model_validate(
        {
            "all": [
                {
                    "any": [
                        {"eq": ["housing_status", "owner"]},
                        {"eq": ["marital_status", "married"]},
                    ]
                },
                {"gte": ["children_count", 1]},
            ]
        }
    )
    assert evaluate_trigger(expr, luis).matched is True


def test_between_boundary_inclusive(luis: ContextProfile) -> None:
    # children_count=2; between [2, 5] → at lower boundary, should match
    expr = Between.model_validate({"between": ["children_count", [2, 5]]})
    assert evaluate_trigger(expr, luis).matched is True


def test_between_boundary_exclusive(luis: ContextProfile) -> None:
    # children_count=2; between [3, 5] → below lower boundary, should not match
    expr = Between.model_validate({"between": ["children_count", [3, 5]]})
    assert evaluate_trigger(expr, luis).matched is False


def test_event_within_years_current_year() -> None:
    current_year = datetime.now().year
    profile = ContextProfile.model_validate(
        {
            "canton": "ZH",
            "employment_status": "employee_full_time",
            "housing_status": "tenant",
            "marital_status": "single",
            "income_band_chf": "50_80k",
            "recent_life_events": [{"event": "had_child", "year": current_year}],
        }
    )
    expr = EventWithinYears.model_validate({"event_within_years": ["had_child", 1]})
    assert evaluate_trigger(expr, profile).matched is True


def test_event_within_years_empty_events() -> None:
    profile = ContextProfile.model_validate(
        {
            "canton": "BE",
            "employment_status": "unemployed",
            "housing_status": "tenant",
            "marital_status": "single",
            "income_band_chf": "lt_30k",
            "recent_life_events": [],
        }
    )
    expr = EventWithinYears.model_validate({"event_within_years": ["had_child", 1]})
    assert evaluate_trigger(expr, profile).matched is False
