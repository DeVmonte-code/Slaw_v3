"use client";
import React, { useState, FormEvent, ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, CheckCircle2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { api, getOrCreateUserId, type ContextProfile } from "@/lib/api-client";
import Link from "next/link";
import {
  CANTONS,
  EMPLOYMENT_OPTIONS,
  HOUSING_OPTIONS,
  MARITAL_OPTIONS,
  INCOME_OPTIONS,
  LIFE_EVENT_OPTIONS,
  NATIONALITY_OPTIONS,
  PERMIT_OPTIONS,
  DEFAULT_PROFILE,
} from "./constants";
import "./wizard.css";

type LifeEvent = NonNullable<ContextProfile["recent_life_events"]>[number];
type LifeEventKind = LifeEvent["event"];

const STEPS = [
  { id: "location", title: "Location & Employment" },
  { id: "residency", title: "Residency & Permit" },
  { id: "housing", title: "Housing" },
  { id: "household", title: "Household & Family" },
  { id: "income", title: "Income & Savings" },
] as const;

const inputClass =
  "w-full rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2.5 text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)] transition-shadow";

function Field({
  label,
  children,
  error,
}: {
  label: string;
  children: ReactNode;
  error?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-[var(--slaw-ink)]">{label}</label>
      <div className={error ? "ring-1 ring-[var(--slaw-danger)] rounded-md" : ""}>{children}</div>
      {error && (
        <span className="text-xs text-[var(--slaw-danger)] mt-0.5">{error}</span>
      )}
    </div>
  );
}

export function SteppedWizard() {
  const router = useRouter();
  const [profile, setProfile] = useState<ContextProfile>(DEFAULT_PROFILE);
  const [stepIndex, setStepIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Task #22 opt-in: when checked, the cleaned profile is also posted to
  // ``/users/{user_id}/profile`` so the nightly sweep picks it up.
  // The user_id is a per-browser UUID stored in localStorage; auth is
  // intentionally out of scope for v1.
  const [notifyEnabled, setNotifyEnabled] = useState(true);

  const update = <K extends keyof ContextProfile>(key: K, value: ContextProfile[K]) => {
    setProfile((prev) => ({ ...prev, [key]: value }));
    if (errors[key as string]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key as string];
        return next;
      });
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const target = e.target;
    const name = target.name as keyof ContextProfile;
    if (target.type === "checkbox") {
      update(name, (target as HTMLInputElement).checked as ContextProfile[typeof name]);
    } else if (target.type === "number") {
      const raw = target.value;
      const num = raw === "" ? undefined : Number(raw);
      update(name, (Number.isNaN(num) ? undefined : num) as ContextProfile[typeof name]);
    } else {
      update(name, target.value as ContextProfile[typeof name]);
    }
  };

  // Strip fields that are no longer applicable based on current selections.
  // Avoids submitting stale tenant/pillar values when those sections are hidden.
  const sanitizeForSubmit = (p: ContextProfile): ContextProfile => {
    const out: ContextProfile = { ...p };
    const isWorking =
      out.employment_status === "employee_full_time" ||
      out.employment_status === "employee_part_time" ||
      out.employment_status === "self_employed" ||
      out.employment_status === "business_owner";
    if (!isWorking) {
      out.employment_start_year = null;
      out.weekly_hours = null;
      out.commute_km_daily = null;
    }
    if (out.housing_status !== "tenant") {
      out.rental_start_year = null;
      out.rent_chf_monthly = null;
      out.lease_reference_rate_tracked = null;
    }
    if (!out.has_third_pillar) {
      out.third_pillar_chf_this_year = null;
    }
    if ((out.children_count ?? 0) <= 0) {
      out.childcare_cost_chf_yearly = null;
      out.children_ages = [];
    }
    // Swiss citizens hold no permit and the years-in-Switzerland number
    // doesn't gate any entitlement for them. Force the canonical values so
    // we never accidentally ship a stale "B permit / 3 years" from a user
    // who flipped back to Swiss after experimenting.
    if (out.nationality_status === "swiss") {
      out.permit_type = "none";
      out.years_in_switzerland = null;
    }
    return out;
  };

  const toggleLifeEvent = (kind: LifeEventKind) => {
    setProfile((prev) => {
      const current = prev.recent_life_events ?? [];
      const exists = current.some((e) => e.event === kind);
      const next: LifeEvent[] = exists
        ? current.filter((e) => e.event !== kind)
        : [...current, { event: kind, year: new Date().getFullYear() }];
      return { ...prev, recent_life_events: next };
    });
  };

  const validateStep = (idx: number): Record<string, string> => {
    const e: Record<string, string> = {};
    const currentYear = new Date().getFullYear();
    const num = (v: unknown) => (v === undefined || v === null ? NaN : Number(v));

    if (idx === 0) {
      if (!profile.canton) e.canton = "Select your canton.";
      if (!profile.employment_status) e.employment_status = "Select your employment status.";
      const isWorking =
        profile.employment_status === "employee_full_time" ||
        profile.employment_status === "employee_part_time" ||
        profile.employment_status === "self_employed" ||
        profile.employment_status === "business_owner";
      if (isWorking) {
        const sy = num(profile.employment_start_year);
        if (!Number.isFinite(sy) || sy < 1950 || sy > currentYear) {
          e.employment_start_year = `Year must be between 1950 and ${currentYear}.`;
        }
        const wh = num(profile.weekly_hours);
        if (!Number.isFinite(wh) || wh < 0 || wh > 80) {
          e.weekly_hours = "Weekly hours must be between 0 and 80.";
        }
        const cm = num(profile.commute_km_daily);
        if (!Number.isFinite(cm) || cm < 0 || cm > 500) {
          e.commute_km_daily = "Commute must be between 0 and 500 km.";
        }
      }
    }
    if (idx === 1) {
      if (!profile.nationality_status) {
        e.nationality_status = "Select your nationality status.";
      }
      if (profile.nationality_status !== "swiss") {
        if (!profile.permit_type) {
          e.permit_type = "Select your permit type.";
        }
        // Required for non-Swiss because naturalisation, family-reunification,
        // and source-tax thresholds all gate on a numeric years count.
        // Swiss residents may leave it blank (handled by the outer branch).
        if (
          profile.years_in_switzerland === null ||
          profile.years_in_switzerland === undefined
        ) {
          e.years_in_switzerland = "Enter how many years you have lived in Switzerland.";
        } else {
          const ys = num(profile.years_in_switzerland);
          if (!Number.isInteger(ys) || ys < 0 || ys > 100) {
            e.years_in_switzerland = "Years must be a whole number between 0 and 100.";
          }
        }
      }
    }
    if (idx === 2) {
      if (!profile.housing_status) e.housing_status = "Select your housing status.";
      if (profile.housing_status === "tenant") {
        const ry = num(profile.rental_start_year);
        if (!Number.isFinite(ry) || ry < 1950 || ry > currentYear) {
          e.rental_start_year = `Year must be between 1950 and ${currentYear}.`;
        }
        const rent = num(profile.rent_chf_monthly);
        if (!Number.isFinite(rent) || rent < 0 || rent > 50000) {
          e.rent_chf_monthly = "Rent must be between CHF 0 and 50,000.";
        }
      }
    }
    if (idx === 3) {
      if (!profile.marital_status) e.marital_status = "Select your marital status.";
      const hs = num(profile.household_size);
      if (!Number.isInteger(hs) || hs < 1 || hs > 12) {
        e.household_size = "Household size must be between 1 and 12.";
      }
      const cc = num(profile.children_count);
      if (!Number.isInteger(cc) || cc < 0 || cc > 10) {
        e.children_count = "Children count must be between 0 and 10.";
      }
      if (cc > 0) {
        const cost = num(profile.childcare_cost_chf_yearly);
        if (!Number.isFinite(cost) || cost < 0) {
          e.childcare_cost_chf_yearly = "Childcare cost must be 0 or greater.";
        }
      }
    }
    if (idx === 4) {
      if (!profile.income_band_chf) e.income_band_chf = "Select your income band.";
      if (profile.has_third_pillar) {
        const p3 = num(profile.third_pillar_chf_this_year);
        if (!Number.isFinite(p3) || p3 < 0 || p3 > 35280) {
          e.third_pillar_chf_this_year = "Pillar 3a must be between CHF 0 and 35,280.";
        }
      }
    }
    return e;
  };

  const next = () => {
    const stepErrors = validateStep(stepIndex);
    if (Object.keys(stepErrors).length > 0) {
      setErrors(stepErrors);
      return;
    }
    setErrors({});
    if (stepIndex < STEPS.length - 1) {
      setDirection(1);
      setStepIndex((s) => s + 1);
    }
  };

  const prev = () => {
    if (stepIndex > 0) {
      setDirection(-1);
      setStepIndex((s) => s - 1);
    }
  };

  const handleSubmit = async (evt?: FormEvent) => {
    evt?.preventDefault();
    // Run validation across every step to guard against stale prior-step values.
    const allErrors: Record<string, string> = {};
    for (let i = 0; i < STEPS.length; i++) {
      Object.assign(allErrors, validateStep(i));
    }
    if (Object.keys(allErrors).length > 0) {
      setErrors(allErrors);
      // Jump back to the first step that has an error so the user can fix it.
      for (let i = 0; i < STEPS.length; i++) {
        if (Object.keys(validateStep(i)).length > 0) {
          setDirection(i < stepIndex ? -1 : 1);
          setStepIndex(i);
          break;
        }
      }
      return;
    }
    setErrors({});
    setSubmitError(null);
    setIsSubmitting(true);
    const cleaned = sanitizeForSubmit(profile);
    const { data, error } = await api.POST("/scan", { body: cleaned });
    if (error || !data) {
      setIsSubmitting(false);
      setSubmitError(String(error ?? "Unknown error — is the backend running?"));
      return;
    }
    // Persist the profile for the nightly sweep. We always upsert (not
    // only when opting in) so flipping the toggle off here propagates
    // ``notify_enabled=false`` to the backend and stops the sweep for
    // returning users. Failure to register is non-fatal: /scan already
    // succeeded above.
    const userId = getOrCreateUserId();
    if (userId) {
      try {
        await api.POST("/users/{user_id}/profile", {
          params: { path: { user_id: userId } },
          body: { profile: cleaned, notify_enabled: notifyEnabled },
        });
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn("sweep_profile_upsert_failed", e);
      }
    }
    setIsSubmitting(false);
    sessionStorage.setItem("benefit_report", JSON.stringify(data));
    router.push("/results");
  };

  const variants = {
    enter: (dir: number) => ({ x: dir > 0 ? 50 : -50, opacity: 0 }),
    center: { x: 0, opacity: 1 },
    exit: (dir: number) => ({ x: dir < 0 ? 50 : -50, opacity: 0 }),
  };

  return (
    <div className="slaw-wizard flex min-h-[100dvh] flex-col bg-[var(--slaw-bg)] antialiased text-[var(--slaw-ink)]">
      <header className="flex-none px-6 pt-8 pb-4 mx-auto w-full max-w-2xl">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold text-[var(--slaw-primary-strong)] tracking-tight">
            Slaw
          </h1>
          <span className="text-xs font-medium uppercase tracking-wider text-[var(--slaw-ink-soft)]">
            Rights Scan
          </span>
        </div>

        <div className="relative">
          <div className="absolute top-1/2 left-0 h-0.5 w-full -translate-y-1/2 bg-[var(--slaw-line)] rounded-full overflow-hidden">
            <div
              className="h-full bg-[var(--slaw-primary)] transition-all duration-500 ease-in-out"
              style={{ width: `${(stepIndex / (STEPS.length - 1)) * 100}%` }}
            />
          </div>
          <div className="relative flex justify-between">
            {STEPS.map((step, idx) => {
              const isCompleted = idx < stepIndex;
              const isCurrent = idx === stepIndex;
              return (
                <div
                  key={step.id}
                  className="flex flex-col items-center gap-2 bg-[var(--slaw-bg)] px-1 z-10"
                >
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
            {STEPS[stepIndex].title}
          </h2>
          <span className="text-sm font-medium text-[var(--slaw-ink-soft)]">
            Step {stepIndex + 1} of {STEPS.length}
          </span>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-2xl px-6 py-4 relative overflow-x-hidden">
        <form onSubmit={handleSubmit} className="relative min-h-[420px]">
          <AnimatePresence mode="wait" custom={direction} initial={false}>
            <motion.div
              key={stepIndex}
              custom={direction}
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{
                x: { type: "spring", stiffness: 300, damping: 30 },
                opacity: { duration: 0.2 },
              }}
              className="w-full"
            >
              <div className="space-y-6 pb-8">
                {stepIndex === 0 && (
                  <div className="flex flex-col gap-5">
                    <Field label="Canton of Residence" error={errors.canton}>
                      <select
                        name="canton"
                        value={profile.canton}
                        onChange={handleChange}
                        className={inputClass}
                      >
                        {CANTONS.map((c) => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    </Field>

                    <Field label="Employment Status" error={errors.employment_status}>
                      <select
                        name="employment_status"
                        value={profile.employment_status}
                        onChange={handleChange}
                        className={inputClass}
                      >
                        {EMPLOYMENT_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </Field>

                    <div className="grid grid-cols-2 gap-4">
                      <Field label="Start Year" error={errors.employment_start_year}>
                        <input
                          name="employment_start_year"
                          type="number"
                          value={profile.employment_start_year ?? ""}
                          onChange={handleChange}
                          className={inputClass}
                        />
                      </Field>
                      <Field label="Weekly Hours" error={errors.weekly_hours}>
                        <input
                          name="weekly_hours"
                          type="number"
                          value={profile.weekly_hours ?? ""}
                          onChange={handleChange}
                          className={inputClass}
                        />
                      </Field>
                    </div>

                    <Field label="Daily Commute (km)" error={errors.commute_km_daily}>
                      <input
                        name="commute_km_daily"
                        type="number"
                        value={profile.commute_km_daily ?? ""}
                        onChange={handleChange}
                        className={inputClass}
                      />
                    </Field>
                  </div>
                )}

                {stepIndex === 1 && (
                  <div className="flex flex-col gap-5">
                    <Field
                      label="Nationality / Residency Status"
                      error={errors.nationality_status}
                    >
                      <select
                        name="nationality_status"
                        value={profile.nationality_status}
                        onChange={handleChange}
                        className={inputClass}
                      >
                        {NATIONALITY_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </Field>

                    {profile.nationality_status !== "swiss" && (
                      <>
                        <Field label="Residence Permit" error={errors.permit_type}>
                          <select
                            name="permit_type"
                            value={profile.permit_type ?? "none"}
                            onChange={handleChange}
                            className={inputClass}
                          >
                            {PERMIT_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        </Field>

                        <Field
                          label="Years living in Switzerland"
                          error={errors.years_in_switzerland}
                        >
                          <input
                            name="years_in_switzerland"
                            type="number"
                            min={0}
                            max={100}
                            value={profile.years_in_switzerland ?? ""}
                            onChange={handleChange}
                            className={inputClass}
                            placeholder="e.g. 5"
                          />
                          <span className="text-xs text-[var(--slaw-ink-soft)] mt-1 block">
                            Used to check naturalisation, family-reunification
                            and source-tax thresholds. Use 0 if you arrived
                            this year.
                          </span>
                        </Field>
                      </>
                    )}

                    {profile.nationality_status === "swiss" && (
                      <p className="text-xs text-[var(--slaw-ink-soft)] rounded-md bg-[var(--slaw-line)] px-3 py-2">
                        Swiss citizens don&rsquo;t need a residence permit, so
                        we&rsquo;ll skip those questions.
                      </p>
                    )}
                  </div>
                )}

                {stepIndex === 2 && (
                  <div className="flex flex-col gap-5">
                    <Field label="Housing Status" error={errors.housing_status}>
                      <select
                        name="housing_status"
                        value={profile.housing_status}
                        onChange={handleChange}
                        className={inputClass}
                      >
                        {HOUSING_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </Field>

                    {profile.housing_status === "tenant" && (
                      <>
                        <div className="grid grid-cols-2 gap-4">
                          <Field label="Rental Start Year" error={errors.rental_start_year}>
                            <input
                              name="rental_start_year"
                              type="number"
                              value={profile.rental_start_year ?? ""}
                              onChange={handleChange}
                              className={inputClass}
                            />
                          </Field>
                          <Field label="Monthly Rent (CHF)" error={errors.rent_chf_monthly}>
                            <input
                              name="rent_chf_monthly"
                              type="number"
                              value={profile.rent_chf_monthly ?? ""}
                              onChange={handleChange}
                              className={inputClass}
                            />
                          </Field>
                        </div>

                        <label className="flex items-start gap-3 mt-2 rounded-md border border-[var(--slaw-line)] bg-white p-4 shadow-sm cursor-pointer hover:border-[var(--slaw-primary-soft)] transition-colors">
                          <input
                            name="lease_reference_rate_tracked"
                            type="checkbox"
                            checked={!!profile.lease_reference_rate_tracked}
                            onChange={handleChange}
                            className="mt-0.5 h-4 w-4 rounded border-gray-300 text-[var(--slaw-primary)] focus:ring-[var(--slaw-primary)] cursor-pointer"
                          />
                          <div className="flex flex-col">
                            <span className="text-sm font-medium text-[var(--slaw-ink)]">
                              Reference rate tracked
                            </span>
                            <span className="text-xs text-[var(--slaw-ink-soft)] mt-0.5">
                              Check if your lease specifically links rent to the federal reference rate.
                            </span>
                          </div>
                        </label>
                      </>
                    )}
                  </div>
                )}

                {stepIndex === 3 && (
                  <div className="flex flex-col gap-5">
                    <Field label="Marital Status" error={errors.marital_status}>
                      <select
                        name="marital_status"
                        value={profile.marital_status}
                        onChange={handleChange}
                        className={inputClass}
                      >
                        {MARITAL_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </Field>

                    <div className="grid grid-cols-2 gap-4">
                      <Field label="Household Size" error={errors.household_size}>
                        <input
                          name="household_size"
                          type="number"
                          min={1}
                          max={12}
                          value={profile.household_size ?? ""}
                          onChange={handleChange}
                          className={inputClass}
                        />
                      </Field>
                      <Field label="Children Count" error={errors.children_count}>
                        <input
                          name="children_count"
                          type="number"
                          min={0}
                          max={10}
                          value={profile.children_count ?? ""}
                          onChange={handleChange}
                          className={inputClass}
                        />
                      </Field>
                    </div>

                    {profile.children_count > 0 && (
                      <Field
                        label="Childcare Cost (CHF/year)"
                        error={errors.childcare_cost_chf_yearly}
                      >
                        <input
                          name="childcare_cost_chf_yearly"
                          type="number"
                          value={profile.childcare_cost_chf_yearly ?? ""}
                          onChange={handleChange}
                          className={inputClass}
                        />
                      </Field>
                    )}

                    <div className="flex flex-col gap-2">
                      <label className="text-sm font-medium text-[var(--slaw-ink)]">
                        Recent life events{" "}
                        <span className="text-xs font-normal text-[var(--slaw-ink-soft)]">
                          (optional)
                        </span>
                      </label>
                      <div className="flex flex-wrap gap-2">
                        {LIFE_EVENT_OPTIONS.map((opt) => {
                          const selected = (profile.recent_life_events ?? []).some(
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

                {stepIndex === 4 && (
                  <div className="flex flex-col gap-5">
                    <Field label="Income Band (CHF/year)" error={errors.income_band_chf}>
                      <select
                        name="income_band_chf"
                        value={profile.income_band_chf}
                        onChange={handleChange}
                        className={inputClass}
                      >
                        {INCOME_OPTIONS.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </Field>

                    <label className="flex items-start gap-3 mt-2 rounded-md border border-[var(--slaw-line)] bg-white p-4 shadow-sm cursor-pointer hover:border-[var(--slaw-primary-soft)] transition-colors">
                      <input
                        name="has_third_pillar"
                        type="checkbox"
                        checked={!!profile.has_third_pillar}
                        onChange={handleChange}
                        className="mt-0.5 h-4 w-4 rounded border-gray-300 text-[var(--slaw-primary)] focus:ring-[var(--slaw-primary)] cursor-pointer"
                      />
                      <div className="flex flex-col">
                        <span className="text-sm font-medium text-[var(--slaw-ink)]">
                          Has 3rd Pillar (Pillar 3a)
                        </span>
                        <span className="text-xs text-[var(--slaw-ink-soft)] mt-0.5">
                          Private pension contributions
                        </span>
                      </div>
                    </label>

                    {profile.has_third_pillar && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        className="pt-2"
                      >
                        <Field
                          label="Contributions This Year (CHF)"
                          error={errors.third_pillar_chf_this_year}
                        >
                          <input
                            name="third_pillar_chf_this_year"
                            type="number"
                            value={profile.third_pillar_chf_this_year ?? ""}
                            onChange={handleChange}
                            className={inputClass}
                          />
                        </Field>
                      </motion.div>
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          </AnimatePresence>

          {submitError && (
            <div className="rounded border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 mb-4">
              {submitError}
            </div>
          )}
        </form>
      </main>

      <footer className="flex-none border-t border-[var(--slaw-line)] bg-white px-6 py-4 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.02)] z-10">
        <div className="mx-auto w-full max-w-2xl">
          <div className="flex items-center justify-between mb-4">
            <button
              type="button"
              onClick={prev}
              disabled={stepIndex === 0 || isSubmitting}
              className={`flex items-center justify-center rounded-md px-4 py-2.5 text-sm font-semibold transition-colors ${
                stepIndex === 0
                  ? "text-[var(--slaw-line-strong)] cursor-not-allowed"
                  : "text-[var(--slaw-ink-soft)] hover:bg-[var(--slaw-line)]"
              }`}
            >
              <ChevronLeft className="mr-1.5 h-4 w-4" />
              Back
            </button>

            {stepIndex < STEPS.length - 1 ? (
              <button
                type="button"
                onClick={next}
                className="flex items-center justify-center rounded-md bg-[var(--slaw-ink)] px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[var(--slaw-ink-soft)] transition-colors"
              >
                Continue
                <ChevronRight className="ml-1.5 h-4 w-4" />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => handleSubmit()}
                disabled={isSubmitting}
                className="flex items-center justify-center rounded-md bg-[var(--slaw-primary)] px-6 py-2.5 text-sm font-semibold text-white shadow-[0_1px_2px_0_rgba(4,120,87,0.3)] hover:bg-[var(--slaw-primary-strong)] disabled:opacity-70 transition-all active:scale-[0.98]"
              >
                {isSubmitting ? "Scanning your rights…" : "Run Rights Scan"}
              </button>
            )}
          </div>

          {stepIndex === STEPS.length - 1 && (
            <div className="mb-3 flex items-center justify-center gap-2 text-xs text-[var(--slaw-ink-soft)]">
              <input
                id="notify-enabled"
                type="checkbox"
                checked={notifyEnabled}
                onChange={(e) => setNotifyEnabled(e.target.checked)}
                className="h-3.5 w-3.5 accent-[var(--slaw-primary)]"
              />
              <label htmlFor="notify-enabled" className="cursor-pointer">
                Notify me when my rights change (nightly sweep)
              </label>
              <span className="text-[var(--slaw-line-strong)]">·</span>
              <Link
                href="/alerts"
                className="text-[var(--slaw-primary-strong)] hover:underline"
              >
                View alerts
              </Link>
            </div>
          )}

          <p className="text-center text-[10px] leading-relaxed text-[var(--slaw-ink-soft)] opacity-80 max-w-[280px] mx-auto">
            Not a substitute for advice from a Swiss attorney registered with a cantonal bar.
          </p>
        </div>
      </footer>
    </div>
  );
}
