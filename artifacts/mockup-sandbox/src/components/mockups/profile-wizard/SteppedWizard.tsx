import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, CheckCircle2 } from "lucide-react";
import "./_group.css";
import type { ContextProfile, LifeEvent, LifeEventKind } from "./types";
import { DEFAULT_CONTEXT_PROFILE } from "./types";

const LIFE_EVENT_OPTIONS: { value: LifeEventKind; label: string }[] = [
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

const CANTONS = [
  "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR", "JU", "LU",
  "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG", "TI", "UR", "VD", "VS", "ZG", "ZH",
];

const EMPLOYMENT_OPTIONS = [
  { value: "employee_full_time", label: "Employee (full-time)" },
  { value: "employee_part_time", label: "Employee (part-time)" },
  { value: "self_employed", label: "Self-employed" },
  { value: "business_owner", label: "Business owner" },
  { value: "unemployed", label: "Unemployed" },
  { value: "student", label: "Student" },
  { value: "retired", label: "Retired" },
];

const HOUSING_OPTIONS = [
  { value: "tenant", label: "Tenant" },
  { value: "owner", label: "Owner" },
  { value: "living_with_family", label: "Living with family" },
];

const MARITAL_OPTIONS = [
  { value: "single", label: "Single" },
  { value: "married", label: "Married" },
  { value: "registered_partnership", label: "Registered partnership" },
  { value: "divorced", label: "Divorced" },
  { value: "widowed", label: "Widowed" },
];

const INCOME_OPTIONS = [
  { value: "lt_30k", label: "Under CHF 30,000" },
  { value: "30_50k", label: "CHF 30,000–50,000" },
  { value: "50_80k", label: "CHF 50,000–80,000" },
  { value: "80_120k", label: "CHF 80,000–120,000" },
  { value: "120_200k", label: "CHF 120,000–200,000" },
  { value: "gt_200k", label: "Over CHF 200,000" },
];

const STEPS = [
  { id: "location", title: "Location & Employment" },
  { id: "housing", title: "Housing" },
  { id: "household", title: "Household & Family" },
  { id: "income", title: "Income & Savings" },
];

export default function SteppedWizard() {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const [formData, setFormData] = useState<ContextProfile>(DEFAULT_CONTEXT_PROFILE);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const target = e.target;
    const isCheckbox = target.type === "checkbox";
    const isNumber = target.type === "number";
    const raw: string | boolean = isCheckbox
      ? (target as HTMLInputElement).checked
      : target.value;
    const value: string | number | boolean =
      isNumber && typeof raw === "string" ? Number(raw) : raw;
    setFormData((prev) => ({
      ...prev,
      [target.name]: value,
    } as ContextProfile));
    if (errors[target.name]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[target.name];
        return next;
      });
    }
  };

  const toggleLifeEvent = (kind: LifeEventKind) => {
    setFormData((prev) => {
      const exists = prev.recent_life_events.some((e) => e.event === kind);
      const next: LifeEvent[] = exists
        ? prev.recent_life_events.filter((e) => e.event !== kind)
        : [
            ...prev.recent_life_events,
            { event: kind, year: new Date().getFullYear() },
          ];
      return { ...prev, recent_life_events: next };
    });
  };

  const validateStep = (stepIndex: number): Record<string, string> => {
    const e: Record<string, string> = {};
    const currentYear = new Date().getFullYear();
    const num = (v: unknown) => Number(v);

    if (stepIndex === 0) {
      if (!formData.canton) e.canton = "Select your canton.";
      if (!formData.employment_status) e.employment_status = "Select your employment status.";
      const sy = num(formData.employment_start_year);
      if (!Number.isFinite(sy) || sy < 1950 || sy > currentYear) {
        e.employment_start_year = `Year must be between 1950 and ${currentYear}.`;
      }
      const wh = num(formData.weekly_hours);
      if (!Number.isFinite(wh) || wh < 0 || wh > 80) {
        e.weekly_hours = "Weekly hours must be between 0 and 80.";
      }
      const cm = num(formData.commute_km_daily);
      if (!Number.isFinite(cm) || cm < 0 || cm > 500) {
        e.commute_km_daily = "Commute must be between 0 and 500 km.";
      }
    }
    if (stepIndex === 1) {
      if (!formData.housing_status) e.housing_status = "Select your housing status.";
      if (formData.housing_status === "tenant") {
        const ry = num(formData.rental_start_year);
        if (!Number.isFinite(ry) || ry < 1950 || ry > currentYear) {
          e.rental_start_year = `Year must be between 1950 and ${currentYear}.`;
        }
        const rent = num(formData.rent_chf_monthly);
        if (!Number.isFinite(rent) || rent < 0 || rent > 50000) {
          e.rent_chf_monthly = "Rent must be between CHF 0 and 50,000.";
        }
      }
    }
    if (stepIndex === 2) {
      if (!formData.marital_status) e.marital_status = "Select your marital status.";
      const hs = num(formData.household_size);
      if (!Number.isInteger(hs) || hs < 1 || hs > 12) {
        e.household_size = "Household size must be between 1 and 12.";
      }
      const cc = num(formData.children_count);
      if (!Number.isInteger(cc) || cc < 0 || cc > 10) {
        e.children_count = "Children count must be between 0 and 10.";
      }
      if (cc > 0) {
        const cost = num(formData.childcare_cost_chf_yearly);
        if (!Number.isFinite(cost) || cost < 0) {
          e.childcare_cost_chf_yearly = "Childcare cost must be 0 or greater.";
        }
      }
    }
    if (stepIndex === 3) {
      if (!formData.income_band_chf) e.income_band_chf = "Select your income band.";
      if (formData.has_third_pillar) {
        const p3 = num(formData.third_pillar_chf_this_year);
        if (!Number.isFinite(p3) || p3 < 0 || p3 > 35280) {
          e.third_pillar_chf_this_year = "Pillar 3a must be between CHF 0 and 35,280.";
        }
      }
    }
    return e;
  };

  const nextStep = () => {
    const stepErrors = validateStep(currentStepIndex);
    if (Object.keys(stepErrors).length > 0) {
      setErrors(stepErrors);
      return;
    }
    setErrors({});
    if (currentStepIndex < STEPS.length - 1) {
      setDirection(1);
      setCurrentStepIndex((prev) => prev + 1);
    }
  };

  const prevStep = () => {
    if (currentStepIndex > 0) {
      setDirection(-1);
      setCurrentStepIndex((prev) => prev - 1);
    }
  };

  const handleSubmit = () => {
    const stepErrors = validateStep(currentStepIndex);
    if (Object.keys(stepErrors).length > 0) {
      setErrors(stepErrors);
      return;
    }
    setErrors({});
    setIsSubmitting(true);
    setTimeout(() => {
      setIsSubmitting(false);
      alert("Scan initiated! (Mockup)");
    }, 1500);
  };

  const variants = {
    enter: (direction: number) => ({
      x: direction > 0 ? 50 : -50,
      opacity: 0,
    }),
    center: {
      x: 0,
      opacity: 1,
    },
    exit: (direction: number) => ({
      x: direction < 0 ? 50 : -50,
      opacity: 0,
    }),
  };

  const InputField = ({
    label,
    children,
    error,
  }: {
    label: string;
    children: React.ReactNode;
    error?: string;
  }) => (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-[var(--slaw-ink)]">{label}</label>
      <div className={error ? "ring-1 ring-[var(--slaw-danger)] rounded-md" : ""}>
        {children}
      </div>
      {error && (
        <span className="text-xs text-[var(--slaw-danger)] mt-0.5">{error}</span>
      )}
    </div>
  );

  return (
    <div className="slaw-wizard flex min-h-[100dvh] flex-col bg-[var(--slaw-bg)] font-sans antialiased text-[var(--slaw-ink)]">
      {/* Header */}
      <header className="flex-none px-6 pt-8 pb-4">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold text-[var(--slaw-primary-strong)] tracking-tight">Slaw</h1>
          <span className="text-xs font-medium uppercase tracking-wider text-[var(--slaw-ink-soft)]">
            Rights Scan
          </span>
        </div>

        {/* Progress Indicator */}
        <div className="relative">
          <div className="absolute top-1/2 left-0 h-0.5 w-full -translate-y-1/2 bg-[var(--slaw-line)] rounded-full overflow-hidden">
            <div 
              className="h-full bg-[var(--slaw-primary)] transition-all duration-500 ease-in-out"
              style={{ width: `${(currentStepIndex / (STEPS.length - 1)) * 100}%` }}
            />
          </div>
          <div className="relative flex justify-between">
            {STEPS.map((step, idx) => {
              const isCompleted = idx < currentStepIndex;
              const isCurrent = idx === currentStepIndex;
              return (
                <div key={step.id} className="flex flex-col items-center gap-2 bg-[var(--slaw-bg)] px-1 z-10">
                  <div
                    className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold transition-colors duration-300 ${
                      isCompleted || isCurrent
                        ? "bg-[var(--slaw-primary)] text-white"
                        : "bg-[var(--slaw-line)] text-[var(--slaw-ink-soft)]"
                    }`}
                  >
                    {isCompleted ? <CheckCircle2 className="h-4 w-4" /> : idx + 1}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="mt-4 flex justify-between items-end">
          <h2 className="text-2xl font-bold text-[var(--slaw-ink)]">
            {STEPS[currentStepIndex].title}
          </h2>
          <span className="text-sm font-medium text-[var(--slaw-ink-soft)]">
            Step {currentStepIndex + 1} of {STEPS.length}
          </span>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 overflow-x-hidden relative px-6 py-4">
        <AnimatePresence mode="wait" custom={direction} initial={false}>
          <motion.div
            key={currentStepIndex}
            custom={direction}
            variants={variants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{
              x: { type: "spring", stiffness: 300, damping: 30 },
              opacity: { duration: 0.2 },
            }}
            className="w-full absolute inset-0 px-6 py-4"
          >
            <div className="space-y-6 pb-24">
              
              {currentStepIndex === 0 && (
                <div className="flex flex-col gap-5">
                  <InputField label="Canton of Residence" error={errors.canton}>
                    <select
                      name="canton"
                      value={formData.canton}
                      onChange={handleChange}
                      className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                    >
                      {CANTONS.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </InputField>

                  <InputField label="Employment Status" error={errors.employment_status}>
                    <select
                      name="employment_status"
                      value={formData.employment_status}
                      onChange={handleChange}
                      className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                    >
                      {EMPLOYMENT_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </InputField>

                  <div className="grid grid-cols-2 gap-4">
                    <InputField label="Start Year" error={errors.employment_start_year}>
                      <input
                        name="employment_start_year"
                        type="number"
                        value={formData.employment_start_year}
                        onChange={handleChange}
                        className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                      />
                    </InputField>
                    <InputField label="Weekly Hours" error={errors.weekly_hours}>
                      <input
                        name="weekly_hours"
                        type="number"
                        value={formData.weekly_hours}
                        onChange={handleChange}
                        className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                      />
                    </InputField>
                  </div>

                  <InputField label="Daily Commute (km)" error={errors.commute_km_daily}>
                    <input
                      name="commute_km_daily"
                      type="number"
                      value={formData.commute_km_daily}
                      onChange={handleChange}
                      className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                    />
                  </InputField>
                </div>
              )}

              {currentStepIndex === 1 && (
                <div className="flex flex-col gap-5">
                  <InputField label="Housing Status" error={errors.housing_status}>
                    <select
                      name="housing_status"
                      value={formData.housing_status}
                      onChange={handleChange}
                      className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                    >
                      {HOUSING_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </InputField>

                  <div className="grid grid-cols-2 gap-4">
                    <InputField label="Rental Start Year" error={errors.rental_start_year}>
                      <input
                        name="rental_start_year"
                        type="number"
                        value={formData.rental_start_year}
                        onChange={handleChange}
                        className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                      />
                    </InputField>
                    <InputField label="Monthly Rent (CHF)" error={errors.rent_chf_monthly}>
                      <input
                        name="rent_chf_monthly"
                        type="number"
                        value={formData.rent_chf_monthly}
                        onChange={handleChange}
                        className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                      />
                    </InputField>
                  </div>

                  <label className="flex items-start gap-3 mt-2 rounded-md border border-[var(--slaw-line)] bg-white p-4 shadow-sm cursor-pointer hover:border-[var(--slaw-primary-soft)] transition-colors">
                    <input
                      name="lease_reference_rate_tracked"
                      type="checkbox"
                      checked={formData.lease_reference_rate_tracked}
                      onChange={handleChange}
                      className="mt-0.5 h-4 w-4 rounded border-gray-300 text-[var(--slaw-primary)] focus:ring-[var(--slaw-primary)] cursor-pointer"
                    />
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-[var(--slaw-ink)]">Reference rate tracked</span>
                      <span className="text-xs text-[var(--slaw-ink-soft)] mt-0.5">Check if your lease specifically links rent to the federal reference rate.</span>
                    </div>
                  </label>
                </div>
              )}

              {currentStepIndex === 2 && (
                <div className="flex flex-col gap-5">
                  <InputField label="Marital Status" error={errors.marital_status}>
                    <select
                      name="marital_status"
                      value={formData.marital_status}
                      onChange={handleChange}
                      className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                    >
                      {MARITAL_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </InputField>

                  <div className="grid grid-cols-2 gap-4">
                    <InputField label="Household Size" error={errors.household_size}>
                      <input
                        name="household_size"
                        type="number"
                        min={1}
                        max={12}
                        value={formData.household_size}
                        onChange={handleChange}
                        className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                      />
                    </InputField>
                    <InputField label="Children Count" error={errors.children_count}>
                      <input
                        name="children_count"
                        type="number"
                        min={0}
                        max={10}
                        value={formData.children_count}
                        onChange={handleChange}
                        className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                      />
                    </InputField>
                  </div>

                  <InputField label="Childcare Cost (CHF/year)" error={errors.childcare_cost_chf_yearly}>
                    <input
                      name="childcare_cost_chf_yearly"
                      type="number"
                      value={formData.childcare_cost_chf_yearly}
                      onChange={handleChange}
                      className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                    />
                  </InputField>

                  <div className="flex flex-col gap-2">
                    <label className="text-sm font-medium text-[var(--slaw-ink)]">
                      Recent life events <span className="text-xs font-normal text-[var(--slaw-ink-soft)]">(optional)</span>
                    </label>
                    <div className="flex flex-wrap gap-2">
                      {LIFE_EVENT_OPTIONS.map((opt) => {
                        const selected = formData.recent_life_events.some(
                          (e) => e.event === opt.value,
                        );
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            onClick={() => toggleLifeEvent(opt.value)}
                            className={`px-3 py-1.5 rounded-full border text-xs font-medium transition-all ${
                              selected
                                ? "bg-[var(--slaw-primary-soft)] border-[var(--slaw-primary)] text-[var(--slaw-primary-strong)]"
                                : "bg-white border-[var(--slaw-line-strong)] text-[var(--slaw-ink-soft)] hover:border-[var(--slaw-primary)]"
                            }`}
                          >
                            {opt.label}
                          </button>
                        );
                      })}
                    </div>
                    <span className="text-xs text-[var(--slaw-ink-soft)]">
                      Tap any change from the last 12 months. Leave empty if none apply.
                    </span>
                  </div>
                </div>
              )}

              {currentStepIndex === 3 && (
                <div className="flex flex-col gap-5">
                  <InputField label="Income Band (CHF/year)" error={errors.income_band_chf}>
                    <select
                      name="income_band_chf"
                      value={formData.income_band_chf}
                      onChange={handleChange}
                      className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                    >
                      {INCOME_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </InputField>

                  <label className="flex items-start gap-3 mt-2 rounded-md border border-[var(--slaw-line)] bg-white p-4 shadow-sm cursor-pointer hover:border-[var(--slaw-primary-soft)] transition-colors">
                    <input
                      name="has_third_pillar"
                      type="checkbox"
                      checked={formData.has_third_pillar}
                      onChange={handleChange}
                      className="mt-0.5 h-4 w-4 rounded border-gray-300 text-[var(--slaw-primary)] focus:ring-[var(--slaw-primary)] cursor-pointer"
                    />
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-[var(--slaw-ink)]">Has 3rd Pillar (Pillar 3a)</span>
                      <span className="text-xs text-[var(--slaw-ink-soft)] mt-0.5">Private pension contributions</span>
                    </div>
                  </label>

                  {formData.has_third_pillar && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="pt-2">
                      <InputField label="Contributions This Year (CHF)" error={errors.third_pillar_chf_this_year}>
                        <input
                          name="third_pillar_chf_this_year"
                          type="number"
                          value={formData.third_pillar_chf_this_year}
                          onChange={handleChange}
                          className="w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow"
                        />
                      </InputField>
                    </motion.div>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        </AnimatePresence>
      </main>

      {/* Footer Navigation */}
      <footer className="flex-none border-t border-[var(--slaw-line)] bg-white px-6 py-4 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.02)] z-10">
        <div className="flex items-center justify-between mb-4">
          <button
            onClick={prevStep}
            disabled={currentStepIndex === 0}
            className={`flex items-center justify-center rounded-md px-4 py-2.5 text-sm font-semibold transition-colors ${
              currentStepIndex === 0
                ? "text-[var(--slaw-line-strong)] cursor-not-allowed"
                : "text-[var(--slaw-ink-soft)] hover:bg-[var(--slaw-line)]"
            }`}
          >
            <ChevronLeft className="mr-1.5 h-4 w-4" />
            Back
          </button>

          {currentStepIndex < STEPS.length - 1 ? (
            <button
              onClick={nextStep}
              className="flex items-center justify-center rounded-md bg-[var(--slaw-ink)] px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[var(--slaw-ink-soft)] transition-colors"
            >
              Continue
              <ChevronRight className="ml-1.5 h-4 w-4" />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="flex items-center justify-center rounded-md bg-[var(--slaw-primary)] px-6 py-2.5 text-sm font-semibold text-white shadow-[0_1px_2px_0_rgba(4,120,87,0.3)] hover:bg-[var(--slaw-primary-strong)] disabled:opacity-70 transition-all active:scale-[0.98]"
            >
              {isSubmitting ? "Initiating Scan..." : "Run Rights Scan"}
            </button>
          )}
        </div>
        
        <p className="text-center text-[10px] leading-relaxed text-[var(--slaw-ink-soft)] opacity-80 max-w-[280px] mx-auto">
          Not a substitute for advice from a Swiss attorney registered with a cantonal bar.
        </p>
      </footer>
    </div>
  );
}
