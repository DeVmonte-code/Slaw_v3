import pytest

from swiss_legal_api.schemas import (
    Benefit,
    Citation,
    ContextProfile,
    Entitlement,
)


def test_citation_accepts_valid():
    c = Citation(
        sr_number="220", article="24", paragraph="1",
        language="en",
        quote_under_15_words="Fundamental error allows rescission under specified conditions.",
    )
    assert c.canton == "CH"


def test_citation_rejects_long_quote():
    with pytest.raises(ValueError):
        Citation(
            sr_number="220", article="24",
            language="en",
            quote_under_15_words="a b c d e f g h i j k l m n o p q",
        )


def test_context_profile_minimal():
    p = ContextProfile(
        canton="ZH",
        employment_status="employee_full_time",
        housing_status="tenant",
        marital_status="married",
        income_band_chf="80_120k",
    )
    assert p.language == "de"
    assert p.children_count == 0


def test_entitlement_parses():
    e = Entitlement.model_validate({
        "id": "rent_reduction_reference_rate",
        "title": {"de": "Mietzinsreduktion", "en": "Rent reduction"},
        "category": "tenancy_right",
        "jurisdiction": "CH",
        "source_citations": [{
            "sr_number": "220", "article": "270a", "language": "en",
            "quote_under_15_words": "The tenant may contest the level of the rent.",
        }],
        "trigger": {"all": [{"eq": ["housing_status", "tenant"]}]},
        "estimated_value_chf": {"min": 500, "max": 3000, "per": "year"},
        "required_action": "claim_letter_to_landlord",
    })
    assert e.confidence_floor == 0.6


def test_benefit_requires_citation():
    with pytest.raises(ValueError):
        Benefit(
            entitlement_id="x", title="x", category="tax_deduction",
            estimated_value_chf={"min": 0, "max": 0, "per": "year"},
            confidence=0.7, citations=[], evidence=[],
            required_action="tax_declaration_field", llm_reasoning="...",
        )
