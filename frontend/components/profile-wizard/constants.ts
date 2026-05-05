import type { ContextProfile } from "@/lib/api-client";

export const CANTONS = [
  "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR", "JU", "LU",
  "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG", "TI", "UR", "VD", "VS", "ZG", "ZH",
] as const;

export const EMPLOYMENT_OPTIONS: { value: ContextProfile["employment_status"]; label: string }[] = [
  { value: "employee_full_time", label: "Employee (full-time)" },
  { value: "employee_part_time", label: "Employee (part-time)" },
  { value: "self_employed", label: "Self-employed" },
  { value: "business_owner", label: "Business owner" },
  { value: "unemployed", label: "Unemployed" },
  { value: "student", label: "Student" },
  { value: "retired", label: "Retired" },
];

export const HOUSING_OPTIONS: { value: ContextProfile["housing_status"]; label: string }[] = [
  { value: "tenant", label: "Tenant" },
  { value: "owner", label: "Owner" },
  { value: "living_with_family", label: "Living with family" },
];

export const MARITAL_OPTIONS: { value: ContextProfile["marital_status"]; label: string }[] = [
  { value: "single", label: "Single" },
  { value: "married", label: "Married" },
  { value: "registered_partnership", label: "Registered partnership" },
  { value: "divorced", label: "Divorced" },
  { value: "widowed", label: "Widowed" },
];

export const NATIONALITY_OPTIONS: {
  value: ContextProfile["nationality_status"];
  label: string;
}[] = [
  { value: "swiss", label: "Swiss citizen" },
  { value: "eu_efta", label: "EU / EFTA national" },
  { value: "third_country", label: "Third-country national" },
];

export const PERMIT_OPTIONS: {
  value: ContextProfile["permit_type"];
  label: string;
}[] = [
  { value: "none", label: "No permit / not applicable" },
  { value: "B", label: "B — Residence permit" },
  { value: "C", label: "C — Settlement permit" },
  { value: "L", label: "L — Short-stay permit" },
  { value: "F", label: "F — Provisional admission" },
  { value: "N", label: "N — Asylum seeker" },
  { value: "S", label: "S — Protection status" },
  { value: "G", label: "G — Cross-border commuter" },
  { value: "Ci", label: "Ci — Family of intl. official" },
];

export const INCOME_OPTIONS: { value: ContextProfile["income_band_chf"]; label: string }[] = [
  { value: "lt_30k", label: "Under CHF 30,000" },
  { value: "30_50k", label: "CHF 30,000–50,000" },
  { value: "50_80k", label: "CHF 50,000–80,000" },
  { value: "80_120k", label: "CHF 80,000–120,000" },
  { value: "120_200k", label: "CHF 120,000–200,000" },
  { value: "gt_200k", label: "Over CHF 200,000" },
];

type LifeEventKind =
  | "moved_canton"
  | "had_child"
  | "got_married"
  | "got_divorced"
  | "lost_job"
  | "started_business"
  | "started_studies"
  | "bought_property"
  | "retired";

export const LIFE_EVENT_OPTIONS: { value: LifeEventKind; label: string }[] = [
  { value: "moved_canton",     label: "Moved canton" },
  { value: "had_child",        label: "Had a child" },
  { value: "got_married",      label: "Got married" },
  { value: "got_divorced",     label: "Got divorced" },
  { value: "lost_job",         label: "Lost a job" },
  { value: "started_business", label: "Started a business" },
  { value: "started_studies",  label: "Started studies" },
  { value: "bought_property",  label: "Bought property" },
  { value: "retired",          label: "Retired" },
];

// --- ENRICHMENT CONSTANTS (Phase 2) ----------------------------------------

export const EMPLOYMENT_CONTRACT_TYPE_OPTIONS = [
  { value: "indefinite", label: "Open-ended (indefinite)" },
  { value: "fixed_term", label: "Fixed-term" },
  { value: "apprenticeship", label: "Apprenticeship / traineeship" },
] as const;

export const FRANCHISE_OPTIONS = [
  { value: 300, label: "CHF 300 - minimum" },
  { value: 500, label: "CHF 500" },
  { value: 1000, label: "CHF 1,000" },
  { value: 1500, label: "CHF 1,500" },
  { value: 2000, label: "CHF 2,000" },
  { value: 2500, label: "CHF 2,500 - maximum" },
] as const;

export const DISABILITY_IV_GRADE_OPTIONS = [
  { value: "none", label: "No disability" },
  { value: "40", label: "40% - quarter pension" },
  { value: "50", label: "50% - half pension" },
  { value: "60", label: "60% - three-quarter pension" },
  { value: "70", label: "70%+ - full pension" },
  { value: "full", label: "Full disability" },
] as const;

export const BVG_PLAN_TYPE_OPTIONS = [
  { value: "mandatory_minimum", label: "Mandatory minimum only" },
  { value: "extended", label: "Extended employer plan" },
  { value: "executive", label: "Executive / Kader plan" },
  { value: "none", label: "No pension fund (self-employed)" },
] as const;

export const LEASE_TYPE_OPTIONS = [
  { value: "indefinite", label: "Open-ended" },
  { value: "fixed_term", label: "Fixed-term" },
  { value: "subsidized", label: "Subsidized / gemeinnuetzig" },
] as const;

export const EVENT_CHIP_OPTIONS = [
  { value: "has_received_termination_notice", label: "Received employment termination notice" },
  { value: "is_on_sick_leave", label: "Currently on sick leave" },
  { value: "paternity_leave_taken", label: "Partner took / taking paternity leave" },
  { value: "received_tenancy_termination", label: "Received lease termination notice" },
  { value: "has_property_damage_dispute", label: "Dispute over deposit or property damage" },
  { value: "is_caring_for_dependent_adult", label: "Caring for ill or disabled family member" },
  { value: "is_survivor_with_dependents", label: "Recently widowed with dependents" },
  { value: "kurzarbeit_or_partial_unemployment", label: "On Kurzarbeit / short-time work" },
] as const satisfies readonly {
  value: keyof ContextProfile;
  label: string;
}[];

export const ENRICHMENT_DEFAULTS = {
  employment_contract_type: undefined,
  is_quellensteuer_subject: undefined,
  is_cross_border_commuter: false,
  lease_type: undefined,
  last_rent_increase_year: undefined,
  tenancy_deposit_chf: undefined,
  gross_income_chf_yearly: undefined,
  health_insurance_franchise_chf: undefined,
  home_office_days_weekly: undefined,
  professional_association_fees_chf: undefined,
  alimony_paid_chf_yearly: undefined,
  charitable_donations_chf_yearly: undefined,
  disability_iv_grade: undefined,
  ahv_contribution_gap_years: undefined,
  alv_contribution_months_last_2y: undefined,
  bvg_plan_type: undefined,
  has_received_termination_notice: false,
  is_on_sick_leave: false,
  maternity_expected_date: undefined,
  paternity_leave_taken: false,
  received_tenancy_termination: false,
  has_property_damage_dispute: false,
  is_caring_for_dependent_adult: false,
  is_survivor_with_dependents: false,
  kurzarbeit_or_partial_unemployment: false,
  personal_note: undefined,
} satisfies Partial<ContextProfile>;

export const DEFAULT_PROFILE: ContextProfile = {
  canton: "ZH",
  language: "de",
  employment_status: "employee_full_time",
  employment_start_year: 2018,
  weekly_hours: 42,
  commute_km_daily: 12,
  housing_status: "tenant",
  rental_start_year: 2018,
  lease_reference_rate_tracked: true,
  rent_chf_monthly: 2400,
  household_size: 4,
  children_count: 2,
  children_ages: [],
  marital_status: "married",
  income_band_chf: "120_200k",
  has_third_pillar: true,
  third_pillar_chf_this_year: 7056,
  business_activity: "none",
  childcare_cost_chf_yearly: 18000,
  permit_type: "none",
  nationality_status: "swiss",
  years_in_switzerland: null,
  recent_life_events: [],
  ...ENRICHMENT_DEFAULTS,
};
