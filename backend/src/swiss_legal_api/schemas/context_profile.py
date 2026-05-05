from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Canton = Literal[
    "AG",
    "AI",
    "AR",
    "BE",
    "BL",
    "BS",
    "FR",
    "GE",
    "GL",
    "GR",
    "JU",
    "LU",
    "NE",
    "NW",
    "OW",
    "SG",
    "SH",
    "SO",
    "SZ",
    "TG",
    "TI",
    "UR",
    "VD",
    "VS",
    "ZG",
    "ZH",
]
Language = Literal["de", "fr", "it", "en"]
EmploymentStatus = Literal[
    "employee_full_time",
    "employee_part_time",
    "self_employed",
    "business_owner",
    "unemployed",
    "student",
    "retired",
]
HousingStatus = Literal["tenant", "owner", "living_with_family"]
MaritalStatus = Literal["single", "married", "registered_partnership", "divorced", "widowed"]
IncomeBand = Literal["lt_30k", "30_50k", "50_80k", "80_120k", "120_200k", "gt_200k"]
BusinessActivity = Literal["none", "freelance", "sole_proprietor", "gmbh", "ag"]
# Residence permits per Ausländer- und Integrationsgesetz (AIG, SR 142.20).
# "none" stands in for Swiss citizens (who hold no permit) and for unspecified
# fixtures; entitlements that depend on a foreign permit gate against the
# specific letter directly.
PermitType = Literal["none", "B", "C", "L", "F", "N", "S", "G", "Ci"]
NationalityStatus = Literal["swiss", "eu_efta", "third_country"]
LifeEventKind = Literal[
    "moved_canton",
    "had_child",
    "got_married",
    "got_divorced",
    "lost_job",
    "started_business",
    "started_studies",
    "bought_property",
    "retired",
]


class LifeEvent(BaseModel):
    event: LifeEventKind
    year: int
    month: int | None = Field(default=None, ge=1, le=12)


class ContextProfile(BaseModel):
    canton: Canton = "ZH"
    language: Language = "de"

    employment_status: EmploymentStatus = "employee_full_time"
    employer_sector: str | None = None
    employment_start_year: int | None = None
    weekly_hours: float | None = Field(default=None, ge=0, le=80)

    housing_status: HousingStatus = "tenant"
    rental_start_year: int | None = None
    lease_reference_rate_tracked: bool | None = None
    rent_chf_monthly: float | None = Field(default=None, ge=0)

    household_size: int = Field(default=1, ge=1, le=12)
    children_count: int = Field(default=0, ge=0, le=10)
    children_ages: list[int] = Field(default_factory=list)
    marital_status: MaritalStatus = "single"

    income_band_chf: IncomeBand = "80_120k"
    has_third_pillar: bool = False
    third_pillar_chf_this_year: float | None = Field(default=None, ge=0)

    business_activity: BusinessActivity = "none"
    rd_spend_chf_this_year: float | None = Field(default=None, ge=0)

    commute_km_daily: float | None = Field(default=None, ge=0)
    childcare_cost_chf_yearly: float | None = Field(default=None, ge=0)

    # Permit-status fields (Option C — added in the permit-status sprint).
    # Default to a Swiss-resident, no-permit baseline so existing fixtures and
    # tests written before the sprint keep passing without migration.
    permit_type: PermitType = "none"
    nationality_status: NationalityStatus = "swiss"
    # User-supplied; not derived from arrival_year. None means unknown / N/A
    # (Swiss citizens leave it blank). Naturalisation triggers gate on a
    # numeric threshold so unknown values correctly fail to match.
    years_in_switzerland: int | None = Field(default=None, ge=0, le=100)

    recent_life_events: list[LifeEvent] = Field(default_factory=list)
    free_text_narrative: str | None = Field(default=None, max_length=2000)

    # --- ENRICHMENT FIELDS (Phase 2) ---
    employment_contract_type: (
        Literal["indefinite", "fixed_term", "apprenticeship"] | None
    ) = None
    is_quellensteuer_subject: bool | None = None
    is_cross_border_commuter: bool = False

    lease_type: Literal["indefinite", "fixed_term", "subsidized"] | None = None
    last_rent_increase_year: int | None = None
    tenancy_deposit_chf: float | None = None

    gross_income_chf_yearly: float | None = None
    health_insurance_franchise_chf: (
        Literal[300, 500, 1000, 1500, 2000, 2500] | None
    ) = None
    home_office_days_weekly: int | None = None
    professional_association_fees_chf: float | None = None
    alimony_paid_chf_yearly: float | None = None
    charitable_donations_chf_yearly: float | None = None

    disability_iv_grade: Literal["none", "40", "50", "60", "70", "full"] | None = None
    ahv_contribution_gap_years: int | None = None
    alv_contribution_months_last_2y: int | None = None
    bvg_plan_type: (
        Literal["mandatory_minimum", "extended", "executive", "none"] | None
    ) = None

    has_received_termination_notice: bool = False
    is_on_sick_leave: bool = False
    maternity_expected_date: str | None = None
    paternity_leave_taken: bool = False
    received_tenancy_termination: bool = False
    has_property_damage_dispute: bool = False
    is_caring_for_dependent_adult: bool = False
    is_survivor_with_dependents: bool = False
    kurzarbeit_or_partial_unemployment: bool = False

    personal_note: str | None = Field(
        default=None,
        max_length=1000,
        description=(
            "Free-text situation description for semantic benefit signal extraction. "
            "Processed at scan time only. Not persisted to any store."
        ),
    )
