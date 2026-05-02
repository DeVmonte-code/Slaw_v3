/**
 * Canonical ContextProfile shape shared by every Profile Wizard variant.
 *
 * Mirrors the `ContextProfile` and `LifeEvent` schemas exported by the
 * backend (see `frontend/lib/api-types.ts`). All four variants must read
 * and write this exact shape so the contract with the `/scan` API stays
 * unchanged regardless of which variant is graduated to production.
 */

export type Canton =
  | "AG" | "AI" | "AR" | "BE" | "BL" | "BS"
  | "FR" | "GE" | "GL" | "GR" | "JU" | "LU"
  | "NE" | "NW" | "OW" | "SG" | "SH" | "SO"
  | "SZ" | "TG" | "TI" | "UR" | "VD" | "VS"
  | "ZG" | "ZH";

export type EmploymentStatus =
  | "employee_full_time"
  | "employee_part_time"
  | "self_employed"
  | "business_owner"
  | "unemployed"
  | "student"
  | "retired";

export type HousingStatus = "tenant" | "owner" | "living_with_family";

export type MaritalStatus =
  | "single"
  | "married"
  | "registered_partnership"
  | "divorced"
  | "widowed";

export type IncomeBand =
  | "lt_30k"
  | "30_50k"
  | "50_80k"
  | "80_120k"
  | "120_200k"
  | "gt_200k";

export type PermitType =
  | "none"
  | "B"
  | "C"
  | "L"
  | "F"
  | "N"
  | "S"
  | "G"
  | "Ci";

export type NationalityStatus = "swiss" | "eu_efta" | "third_country";

export type LifeEventKind =
  | "moved_canton"
  | "had_child"
  | "got_married"
  | "got_divorced"
  | "lost_job"
  | "started_business"
  | "started_studies"
  | "bought_property"
  | "retired";

export interface LifeEvent {
  event: LifeEventKind;
  year: number;
  month?: number | null;
}

export interface ContextProfile {
  canton: Canton;
  employment_status: EmploymentStatus;
  employment_start_year: number;
  weekly_hours: number;
  commute_km_daily: number;

  housing_status: HousingStatus;
  rental_start_year: number;
  rent_chf_monthly: number;
  lease_reference_rate_tracked: boolean;

  marital_status: MaritalStatus;
  household_size: number;
  children_count: number;
  childcare_cost_chf_yearly: number;

  income_band_chf: IncomeBand;
  has_third_pillar: boolean;
  third_pillar_chf_this_year: number;

  permit_type: PermitType;
  nationality_status: NationalityStatus;
  years_in_switzerland: number | null;

  recent_life_events: LifeEvent[];
}

export const DEFAULT_CONTEXT_PROFILE: ContextProfile = {
  canton: "ZH",
  employment_status: "employee_full_time",
  employment_start_year: 2018,
  weekly_hours: 42,
  commute_km_daily: 12,

  housing_status: "tenant",
  rental_start_year: 2018,
  rent_chf_monthly: 2400,
  lease_reference_rate_tracked: true,

  marital_status: "married",
  household_size: 4,
  children_count: 2,
  childcare_cost_chf_yearly: 18000,

  income_band_chf: "120_200k",
  has_third_pillar: true,
  third_pillar_chf_this_year: 7056,

  permit_type: "none",
  nationality_status: "swiss",
  years_in_switzerland: null,

  recent_life_events: [],
};
