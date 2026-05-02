import React, { useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import "./_group.css";
import type { ContextProfile, LifeEvent, LifeEventKind } from "./types";
import { DEFAULT_CONTEXT_PROFILE } from "./types";

const LIFE_EVENT_OPTIONS: { value: LifeEventKind; label: string }[] = [
  { value: "moved_canton",     label: "moved cantons" },
  { value: "had_child",        label: "had a child" },
  { value: "got_married",      label: "got married" },
  { value: "got_divorced",     label: "got divorced" },
  { value: "lost_job",         label: "lost my job" },
  { value: "started_business", label: "started a business" },
  { value: "started_studies",  label: "started studies" },
  { value: "bought_property",  label: "bought property" },
  { value: "retired",          label: "retired" },
];

const CANTONS = [
  "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR", "JU", "LU",
  "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG", "TI", "UR", "VD", "VS", "ZG", "ZH",
];

const EMPLOYMENT_OPTIONS = [
  { value: "employee_full_time", label: "employed full-time" },
  { value: "employee_part_time", label: "employed part-time" },
  { value: "self_employed", label: "self-employed" },
  { value: "business_owner", label: "a business owner" },
  { value: "unemployed", label: "currently unemployed" },
  { value: "student", label: "a student" },
  { value: "retired", label: "retired" },
];

const HOUSING_OPTIONS = [
  { value: "tenant", label: "rent my home" },
  { value: "owner", label: "own my home" },
  { value: "living_with_family", label: "live with family" },
];

const MARITAL_OPTIONS = [
  { value: "single", label: "single" },
  { value: "married", label: "married" },
  { value: "registered_partnership", label: "in a registered partnership" },
  { value: "divorced", label: "divorced" },
  { value: "widowed", label: "widowed" },
];

const INCOME_OPTIONS = [
  { value: "lt_30k", label: "under CHF 30,000" },
  { value: "30_50k", label: "between CHF 30,000 and 50,000" },
  { value: "50_80k", label: "between CHF 50,000 and 80,000" },
  { value: "80_120k", label: "between CHF 80,000 and 120,000" },
  { value: "120_200k", label: "between CHF 120,000 and 200,000" },
  { value: "gt_200k", label: "over CHF 200,000" },
];

function InlineSelect({
  value,
  options,
  onChange,
  prefix = "",
  suffix = "",
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  prefix?: string;
  suffix?: string;
}) {
  const selectedLabel = options.find((o) => o.value === value)?.label || value;

  return (
    <span className="relative inline-block group">
      {prefix && <span>{prefix} </span>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="absolute inset-0 opacity-0 w-full h-full cursor-pointer"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <span className="inline-flex items-center text-emerald-800 font-semibold border-b border-emerald-800/30 group-hover:border-emerald-800 transition-colors">
        {selectedLabel}
        <ChevronDown className="w-3 h-3 ml-0.5 opacity-50 group-hover:opacity-100 transition-opacity" />
      </span>
      {suffix && <span> {suffix}</span>}
    </span>
  );
}

function InlineInput({
  value,
  onChange,
  type = "text",
  prefix = "",
  suffix = "",
  min,
  max,
}: {
  value: string | number;
  onChange: (v: string | number) => void;
  type?: "text" | "number";
  prefix?: string;
  suffix?: string;
  min?: number;
  max?: number;
}) {
  return (
    <span className="relative inline-block group whitespace-nowrap">
      {prefix && <span>{prefix} </span>}
      <span className="inline-flex items-center border-b border-emerald-800/30 group-hover:border-emerald-800 transition-colors text-emerald-800 font-semibold px-0.5">
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(type === "number" ? Number(e.target.value) : e.target.value)}
          min={min}
          max={max}
          className="bg-transparent border-none outline-none p-0 m-0 w-full text-center text-emerald-800 font-semibold focus:ring-0 placeholder-emerald-800/30"
          style={{ width: `${Math.max(String(value).length, 1) + 0.5}ch` }}
        />
      </span>
      {suffix && <span> {suffix}</span>}
    </span>
  );
}

function InlineCheckbox({
  checked,
  onChange,
  labelTrue,
  labelFalse,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  labelTrue: string;
  labelFalse: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className="inline-flex items-center border-b border-emerald-800/30 hover:border-emerald-800 transition-colors text-emerald-800 font-semibold px-0.5"
    >
      {checked ? labelTrue : labelFalse}
    </button>
  );
}

export default function DocumentIntake() {
  const [data, setData] = useState<ContextProfile>(DEFAULT_CONTEXT_PROFILE);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const updateField = <K extends keyof ContextProfile>(
    field: K,
    value: ContextProfile[K],
  ) => {
    setData((prev) => ({ ...prev, [field]: value }));
  };

  const toggleLifeEvent = (kind: LifeEventKind) => {
    setData((prev) => {
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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setTimeout(() => setIsSubmitting(false), 1500);
  };

  return (
    <div className="slaw-wizard min-h-[100dvh] bg-[#fdfbf7] text-[#2c332e] font-serif selection:bg-emerald-100 selection:text-emerald-900">
      {/* Decorative top border */}
      <div className="h-2 w-full bg-emerald-800" />
      
      <main className="mx-auto max-w-2xl px-8 py-16 sm:px-12 sm:py-24">
        <header className="mb-16">
          <p className="text-sm font-sans tracking-widest uppercase text-emerald-800/60 mb-4 flex items-center gap-3">
            <span className="w-8 h-[1px] bg-emerald-800/30 inline-block"></span>
            Profile Declaration
          </p>
          <h1 className="text-4xl sm:text-5xl font-normal leading-tight text-emerald-950">
            Swiss Legal <br />
            <span className="italic opacity-90">Rights Scan</span>
          </h1>
          <p className="mt-6 text-lg sm:text-xl text-[#4a544c] leading-relaxed max-w-lg">
            A comprehensive assessment of your entitlements, deductions, and protections under Swiss federal and cantonal law.
          </p>
        </header>

        <form onSubmit={handleSubmit} className="space-y-12 text-lg sm:text-xl leading-loose text-[#3a443e]">
          <section>
            <p>
              I am a resident of the canton of{" "}
              <InlineSelect
                value={data.canton}
                options={CANTONS.map((c) => ({ value: c, label: c }))}
                onChange={(v) => updateField("canton", v)}
              />
              . Currently, I am{" "}
              <InlineSelect
                value={data.employment_status}
                options={EMPLOYMENT_OPTIONS}
                onChange={(v) => updateField("employment_status", v)}
              />
              , a position I have held since{" "}
              <InlineInput
                type="number"
                value={data.employment_start_year}
                onChange={(v) => updateField("employment_start_year", v)}
                min={1950}
                max={new Date().getFullYear()}
              />
              .
              {["employee_full_time", "employee_part_time"].includes(data.employment_status) && (
                <>
                  {" "}I typically work{" "}
                  <InlineInput
                    type="number"
                    value={data.weekly_hours}
                    onChange={(v) => updateField("weekly_hours", v)}
                    min={1}
                    max={100}
                    suffix="hours per week"
                  />
                  {" "}and commute approximately{" "}
                  <InlineInput
                    type="number"
                    value={data.commute_km_daily}
                    onChange={(v) => updateField("commute_km_daily", v)}
                    min={0}
                    max={500}
                    suffix="kilometers daily"
                  />
                  .
                </>
              )}
            </p>
          </section>

          <section>
            <p>
              Regarding my living situation, I{" "}
              <InlineSelect
                value={data.housing_status}
                options={HOUSING_OPTIONS}
                onChange={(v) => updateField("housing_status", v)}
              />
              .{" "}
              {data.housing_status === "tenant" && (
                <>
                  I have lived here since{" "}
                  <InlineInput
                    type="number"
                    value={data.rental_start_year}
                    onChange={(v) => updateField("rental_start_year", v)}
                    min={1950}
                    max={new Date().getFullYear()}
                  />
                  , paying{" "}
                  <InlineInput
                    type="number"
                    value={data.rent_chf_monthly}
                    onChange={(v) => updateField("rent_chf_monthly", v)}
                    min={0}
                    prefix="CHF"
                    suffix="monthly"
                  />
                  . My lease{" "}
                  <InlineCheckbox
                    checked={data.lease_reference_rate_tracked}
                    onChange={(v) => updateField("lease_reference_rate_tracked", v)}
                    labelTrue="is explicitly tied"
                    labelFalse="is not explicitly tied"
                  />
                  {" "}to the Swiss reference interest rate.
                </>
              )}
            </p>
          </section>

          <section>
            <p>
              My household consists of{" "}
              <InlineInput
                type="number"
                value={data.household_size}
                onChange={(v) => updateField("household_size", v)}
                min={1}
                max={12}
                suffix={data.household_size === 1 ? "person" : "people"}
              />
              , and I am legally{" "}
              <InlineSelect
                value={data.marital_status}
                options={MARITAL_OPTIONS}
                onChange={(v) => updateField("marital_status", v)}
              />
              . I have{" "}
              <InlineInput
                type="number"
                value={data.children_count}
                onChange={(v) => updateField("children_count", v)}
                min={0}
                max={10}
                suffix={data.children_count === 1 ? "child" : "children"}
              />
              .{" "}
              {data.children_count > 0 && (
                <>
                  Annual childcare expenses amount to approximately{" "}
                  <InlineInput
                    type="number"
                    value={data.childcare_cost_chf_yearly}
                    onChange={(v) => updateField("childcare_cost_chf_yearly", v)}
                    min={0}
                    prefix="CHF"
                  />
                  .
                </>
              )}
            </p>
          </section>

          <section>
            <p>
              Financially, my annual household income falls{" "}
              <InlineSelect
                value={data.income_band_chf}
                options={INCOME_OPTIONS}
                onChange={(v) => updateField("income_band_chf", v)}
              />
              . This year, I{" "}
              <InlineCheckbox
                checked={data.has_third_pillar}
                onChange={(v) => updateField("has_third_pillar", v)}
                labelTrue="have contributed"
                labelFalse="have not contributed"
              />
              {" "}to a Pillar 3a account
              {data.has_third_pillar && (
                <>
                  , depositing{" "}
                  <InlineInput
                    type="number"
                    value={data.third_pillar_chf_this_year}
                    onChange={(v) => updateField("third_pillar_chf_this_year", v)}
                    min={0}
                    prefix="CHF"
                  />
                </>
              )}
              .
            </p>
          </section>

          <section>
            <p>
              Within the last twelve months, my circumstances have changed in
              the following ways:{" "}
              {LIFE_EVENT_OPTIONS.map((opt, i) => {
                const selected = data.recent_life_events.some(
                  (e) => e.event === opt.value,
                );
                return (
                  <React.Fragment key={opt.value}>
                    <button
                      type="button"
                      onClick={() => toggleLifeEvent(opt.value)}
                      className={
                        selected
                          ? "inline-flex items-center border-b border-emerald-800 text-emerald-800 font-semibold px-0.5 mr-1"
                          : "inline-flex items-center border-b border-emerald-800/20 text-emerald-800/40 font-medium hover:text-emerald-800 hover:border-emerald-800/60 transition-colors px-0.5 mr-1"
                      }
                    >
                      {opt.label}
                    </button>
                    {i < LIFE_EVENT_OPTIONS.length - 1 ? ", " : ""}
                  </React.Fragment>
                );
              })}
              .{" "}
              {data.recent_life_events.length === 0 && (
                <span className="text-[#78857d] italic">
                  (Tap any change above that applies; otherwise none.)
                </span>
              )}
            </p>
          </section>

          <div className="pt-16 pb-8 border-t border-emerald-900/10 mt-16 flex flex-col sm:flex-row items-center justify-between gap-8">
            <p className="text-xs font-sans text-[#78857d] max-w-xs text-center sm:text-left uppercase tracking-wide">
              Not a substitute for advice from a Swiss attorney registered with a cantonal bar.
            </p>
            
            <button
              type="submit"
              disabled={isSubmitting}
              className="relative inline-flex items-center justify-center px-8 py-4 font-sans text-sm font-semibold tracking-wide text-white uppercase transition-all bg-emerald-900 hover:bg-emerald-800 disabled:opacity-70 disabled:cursor-not-allowed group overflow-hidden"
            >
              <span className="relative z-10 flex items-center gap-2">
                {isSubmitting ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Reviewing Rights
                  </>
                ) : (
                  <>
                    Run Rights Scan
                    <Check className="w-4 h-4 opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
                  </>
                )}
              </span>
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
