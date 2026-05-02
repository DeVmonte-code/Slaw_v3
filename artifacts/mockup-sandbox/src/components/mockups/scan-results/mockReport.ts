/**
 * Mock BenefitReport used by every Scan Results variant so the four mockups
 * render identical underlying data side-by-side. Modeled on the seeded
 * entitlements in `backend/seed/entitlements.json` and the canonical Luis
 * profile in `backend/fixtures/luis_profile.json` so the visuals reflect a
 * realistic /scan response shape.
 */

import type { BenefitReport } from "./types";

export const MOCK_REPORT: BenefitReport = {
  generated_at: "2026-05-02T14:32:11.482Z",
  profile_hash: "luis-zh-employee-tenant-married-2-kids",
  suppressed_count: 3,
  benefits: [
    {
      entitlement_id: "third_pillar_deduction",
      title: "Third Pillar (Pillar 3a) Tax Deduction",
      category: "tax_deduction",
      estimated_value_chf: { min: 6000, max: 7056, per: "year" },
      confidence: 0.94,
      required_action: "tax_declaration_field",
      action_template_id: "tax_pillar3a_2026",
      time_limit_days: 240,
      citations: [
        {
          sr_number: "831.40",
          article: "82",
          paragraph: "1",
          canton: "CH",
          language: "en",
          quote_under_15_words:
            "Contributions to tied pension accounts are tax deductible.",
        },
      ],
      evidence: [
        { field: "has_third_pillar", value: true },
        { field: "third_pillar_chf_this_year", value: 7056 },
        { field: "income_band_chf", value: "120_200k" },
      ],
      llm_reasoning:
        "You contributed CHF 7,056 to Pillar 3a this year, which is the full federal cap for employees with a 2nd-pillar plan. Enter the certificate amount on line 16 of your federal tax return; the full contribution reduces taxable income.",
      disclaimer:
        "Not a substitute for advice from a Swiss attorney registered with a cantonal bar.",
    },
    {
      entitlement_id: "childcare_cost_deduction",
      title: "Childcare Cost Deduction",
      category: "tax_deduction",
      estimated_value_chf: { min: 2000, max: 10250, per: "year" },
      confidence: 0.91,
      required_action: "tax_declaration_field",
      action_template_id: "tax_childcare_2026",
      time_limit_days: 240,
      citations: [
        {
          sr_number: "642.11",
          article: "33",
          paragraph: "1",
          canton: "CH",
          language: "en",
          quote_under_15_words:
            "Childcare costs for children under fourteen are tax deductible.",
        },
      ],
      evidence: [
        { field: "children_count", value: 2 },
        { field: "children_ages", value: "3, 6" },
        { field: "childcare_cost_chf_yearly", value: 18000 },
      ],
      llm_reasoning:
        "With two children under 14 and CHF 18,000 of declared external childcare, you can deduct up to CHF 10,250 federally and a higher cantonal cap in ZH. Keep daycare invoices; the deduction is per child, not per household.",
      disclaimer:
        "Not a substitute for advice from a Swiss attorney registered with a cantonal bar.",
    },
    {
      entitlement_id: "rent_reduction_reference_rate",
      title: "Rent Reduction for Reference Rate Change",
      category: "tenancy_right",
      estimated_value_chf: { min: 500, max: 3000, per: "year" },
      confidence: 0.88,
      required_action: "claim_letter_to_landlord",
      action_template_id: "tenant_rent_reduction_letter",
      time_limit_days: 30,
      citations: [
        {
          sr_number: "220",
          article: "270a",
          paragraph: "1",
          canton: "CH",
          language: "en",
          quote_under_15_words:
            "Tenant may challenge rent exceeding the local reference rate.",
        },
      ],
      evidence: [
        { field: "housing_status", value: "tenant" },
        { field: "rental_start_year", value: 2018 },
        { field: "lease_reference_rate_tracked", value: true },
        { field: "rent_chf_monthly", value: 2400 },
      ],
      llm_reasoning:
        "Your lease has tracked the reference rate since 2018 and the rate has dropped twice since then. You can demand a rent reduction in writing — the landlord must reply within 30 days or you escalate to the Schlichtungsbehörde.",
      disclaimer:
        "Not a substitute for advice from a Swiss attorney registered with a cantonal bar.",
    },
    {
      entitlement_id: "commuting_cost_deduction",
      title: "Commuting Cost Deduction",
      category: "tax_deduction",
      estimated_value_chf: { min: 300, max: 3000, per: "year" },
      confidence: 0.86,
      required_action: "tax_declaration_field",
      action_template_id: null,
      time_limit_days: 240,
      citations: [
        {
          sr_number: "642.11",
          article: "26",
          paragraph: "1",
          canton: "CH",
          language: "en",
          quote_under_15_words:
            "Necessary travel costs between home and workplace are deductible.",
        },
      ],
      evidence: [
        { field: "employment_status", value: "employee_full_time" },
        { field: "commute_km_daily", value: 12 },
      ],
      llm_reasoning:
        "Your 12 km daily commute qualifies for the federal Fahrtkostenabzug, capped at CHF 3,000 federally and roughly the same in ZH. Use public-transit costs if higher than the per-km rate.",
      disclaimer:
        "Not a substitute for advice from a Swiss attorney registered with a cantonal bar.",
    },
    {
      entitlement_id: "marriage_taxation_neutralization",
      title: "Married Couple Taxation Neutralization",
      category: "tax_deduction",
      estimated_value_chf: { min: 0, max: 5000, per: "year" },
      confidence: 0.82,
      required_action: "tax_declaration_field",
      action_template_id: null,
      time_limit_days: 240,
      citations: [
        {
          sr_number: "642.11",
          article: "9",
          paragraph: "1",
          canton: "CH",
          language: "en",
          quote_under_15_words:
            "Spouses are taxed jointly on combined income and assets.",
        },
      ],
      evidence: [
        { field: "marital_status", value: "married" },
        { field: "income_band_chf", value: "120_200k" },
      ],
      llm_reasoning:
        "Joint taxation can produce either a marriage penalty or a marriage bonus depending on the split. With one main earner in your bracket, the federal marital deduction (Verheiratetenabzug) and split tariff give you up to CHF 5,000.",
      disclaimer:
        "Not a substitute for advice from a Swiss attorney registered with a cantonal bar.",
    },
    {
      entitlement_id: "employer_health_protection",
      title: "Employer Duty to Protect Employee Health",
      category: "employment_right",
      estimated_value_chf: { min: 0, max: 5000, per: "year" },
      confidence: 0.79,
      required_action: "employer_request",
      action_template_id: null,
      time_limit_days: null,
      citations: [
        {
          sr_number: "220",
          article: "328",
          paragraph: "1",
          canton: "CH",
          language: "en",
          quote_under_15_words:
            "Employer shall protect employees' health and personal integrity.",
        },
      ],
      evidence: [
        { field: "employment_status", value: "employee_full_time" },
        { field: "weekly_hours", value: 42 },
      ],
      llm_reasoning:
        "At 42 weekly hours your employer owes a documented health-protection plan: ergonomic workstation, screen-break schedule, and access to occupational medicine. You can formally request the assessment in writing.",
      disclaimer:
        "Not a substitute for advice from a Swiss attorney registered with a cantonal bar.",
    },
    {
      entitlement_id: "overtime_compensation",
      title: "Overtime Compensation",
      category: "employment_right",
      estimated_value_chf: { min: 800, max: 4000, per: "year" },
      confidence: 0.76,
      required_action: "employer_request",
      action_template_id: "employer_overtime_letter",
      time_limit_days: 1825,
      citations: [
        {
          sr_number: "220",
          article: "321c",
          paragraph: "1",
          canton: "CH",
          language: "en",
          quote_under_15_words:
            "Employee must be compensated for overtime with pay or time off.",
        },
      ],
      evidence: [
        { field: "employment_status", value: "employee_full_time" },
        { field: "weekly_hours", value: 42 },
      ],
      llm_reasoning:
        "Hours above 40/week count as overtime unless your contract opts you out in writing. Default compensation is salary + 25% surcharge or equivalent time off. Five-year limitation period.",
      disclaimer:
        "Not a substitute for advice from a Swiss attorney registered with a cantonal bar.",
    },
    {
      entitlement_id: "rent_deposit_interest",
      title: "Interest on Rental Deposit",
      category: "tenancy_right",
      estimated_value_chf: { min: 50, max: 300, per: "year" },
      confidence: 0.74,
      required_action: "claim_letter_to_landlord",
      action_template_id: null,
      time_limit_days: null,
      citations: [
        {
          sr_number: "220",
          article: "257e",
          paragraph: "1",
          canton: "CH",
          language: "en",
          quote_under_15_words:
            "Landlord must deposit rental security and pay interest thereon.",
        },
      ],
      evidence: [
        { field: "housing_status", value: "tenant" },
        { field: "rent_chf_monthly", value: 2400 },
      ],
      llm_reasoning:
        "Your deposit must sit in a Mietkautionskonto in your name and accrue savings-account interest. Request the annual statement from the bank — the landlord cannot keep the interest.",
      disclaimer:
        "Not a substitute for advice from a Swiss attorney registered with a cantonal bar.",
    },
    {
      entitlement_id: "professional_training_deduction",
      title: "Professional Training Cost Deduction",
      category: "tax_deduction",
      estimated_value_chf: { min: 500, max: 12000, per: "year" },
      confidence: 0.71,
      required_action: "tax_declaration_field",
      action_template_id: null,
      time_limit_days: 240,
      citations: [
        {
          sr_number: "642.11",
          article: "33a",
          paragraph: "1",
          canton: "CH",
          language: "en",
          quote_under_15_words:
            "Costs of further education and training may be deducted.",
        },
      ],
      evidence: [
        { field: "employment_status", value: "employee_full_time" },
      ],
      llm_reasoning:
        "Job-related courses, certifications, and continuing education are deductible up to CHF 12,000 federally — even if not reimbursed by the employer. Save invoices and any course confirmation.",
      disclaimer:
        "Not a substitute for advice from a Swiss attorney registered with a cantonal bar.",
    },
    {
      entitlement_id: "notice_period_seniority",
      title: "Extended Notice Period by Seniority",
      category: "employment_right",
      estimated_value_chf: { min: 1000, max: 3000, per: "one_time" },
      confidence: 0.68,
      required_action: "employer_request",
      action_template_id: null,
      time_limit_days: null,
      citations: [
        {
          sr_number: "220",
          article: "335c",
          paragraph: "1",
          canton: "CH",
          language: "en",
          quote_under_15_words:
            "Notice period is one month in the first year of service.",
        },
      ],
      evidence: [
        { field: "employment_status", value: "employee_full_time" },
        { field: "employment_start_year", value: 2018 },
      ],
      llm_reasoning:
        "Eight years of service moves your statutory notice period from one to three months. Confirm in writing if your contract still says one month — the statute overrides shorter periods.",
      disclaimer:
        "Not a substitute for advice from a Swiss attorney registered with a cantonal bar.",
    },
  ],
};
