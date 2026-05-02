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
  recent_life_events: [],
};
