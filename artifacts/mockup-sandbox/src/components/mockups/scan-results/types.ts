/**
 * Canonical BenefitReport shape shared by every Scan Results variant.
 *
 * Mirrors the `BenefitReport`, `Benefit`, `Citation`, `EvidenceItem` and
 * `EstimatedValue` schemas exported by the backend (see
 * `frontend/lib/api-types.ts`). All four results variants must read this
 * exact shape so the contract with the `/scan` API stays unchanged regardless
 * of which variant is graduated to production.
 */

export type BenefitCategory =
  | "tax_deduction"
  | "tenancy_right"
  | "employment_right"
  | "family_benefit"
  | "business_subsidy"
  | "social_security"
  | "consumer_protection";

export type RequiredAction =
  | "claim_letter_to_landlord"
  | "tax_declaration_field"
  | "employer_request"
  | "cantonal_application"
  | "federal_application"
  | "consultation_with_lawyer";

export type CitationLanguage = "de" | "fr" | "it" | "en";

export interface Citation {
  sr_number: string;
  article: string;
  paragraph?: string | null;
  canton: string;
  language: CitationLanguage;
  quote_under_15_words: string;
}

export interface EvidenceItem {
  field: string;
  value: string | number | boolean | null;
}

export interface EstimatedValue {
  min: number;
  max: number;
  per: "year" | "one_time" | "month";
}

export interface Benefit {
  entitlement_id: string;
  title: string;
  category: BenefitCategory;
  estimated_value_chf: EstimatedValue;
  confidence: number;
  citations: Citation[];
  evidence: EvidenceItem[];
  required_action: RequiredAction;
  action_template_id?: string | null;
  time_limit_days?: number | null;
  llm_reasoning: string;
  disclaimer: string;
}

export interface BenefitReport {
  generated_at: string;
  profile_hash: string;
  benefits: Benefit[];
  suppressed_count: number;
}

export const CATEGORY_LABELS: Record<BenefitCategory, string> = {
  tax_deduction: "Tax Deduction",
  tenancy_right: "Tenancy Right",
  employment_right: "Employment Right",
  family_benefit: "Family Benefit",
  business_subsidy: "Business Subsidy",
  social_security: "Social Security",
  consumer_protection: "Consumer Protection",
};

export const ACTION_LABELS: Record<RequiredAction, string> = {
  claim_letter_to_landlord: "Send letter to landlord",
  tax_declaration_field: "Enter in tax declaration",
  employer_request: "Request from employer",
  cantonal_application: "Apply at cantonal authority",
  federal_application: "Apply at federal authority",
  consultation_with_lawyer: "Consult a lawyer",
};

export function midpointValue(v: EstimatedValue): number {
  return Math.round((v.min + v.max) / 2);
}

export function impactScore(b: Benefit): number {
  return midpointValue(b.estimated_value_chf) * b.confidence;
}

export function formatChf(n: number): string {
  return new Intl.NumberFormat("en-CH", {
    maximumFractionDigits: 0,
  }).format(n);
}
