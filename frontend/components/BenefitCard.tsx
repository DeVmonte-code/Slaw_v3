import { useState } from "react";
import type { Benefit } from "@/lib/api-client";
import { AskFollowUp } from "./AskFollowUp";

type ConfidenceTone = {
  ring: string;
  text: string;
  bg: string;
  label: string;
};

function confidenceTone(c: number): ConfidenceTone {
  if (c >= 0.85)
    return {
      ring: "#047857",
      text: "text-emerald-800",
      bg: "bg-emerald-50",
      label: "High confidence",
    };
  if (c >= 0.7)
    return {
      ring: "#b45309",
      text: "text-amber-800",
      bg: "bg-amber-50",
      label: "Medium confidence",
    };
  return {
    ring: "#c2410c",
    text: "text-orange-800",
    bg: "bg-orange-50",
    label: "Lower confidence",
  };
}

const CATEGORY_LABELS: Record<string, string> = {
  tax_deduction: "Tax Deduction",
  tenancy_right: "Tenancy Right",
  employment_right: "Employment Right",
  family_benefit: "Family Benefit",
  business_subsidy: "Business Subsidy",
  social_security: "Social Security",
  consumer_protection: "Consumer Protection",
};

const CATEGORY_TONES: Record<string, string> = {
  tax_deduction: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  tenancy_right: "bg-sky-50 text-sky-700 ring-sky-200",
  employment_right: "bg-violet-50 text-violet-700 ring-violet-200",
  family_benefit: "bg-rose-50 text-rose-700 ring-rose-200",
  business_subsidy: "bg-teal-50 text-teal-700 ring-teal-200",
  social_security: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  consumer_protection: "bg-amber-50 text-amber-800 ring-amber-200",
};

const ACTION_LABELS: Record<string, string> = {
  claim_letter_to_landlord: "Send a claim letter to your landlord",
  tax_declaration_field: "Enter this in your tax declaration",
  employer_request: "Request this from your employer",
  cantonal_application: "Apply at the cantonal authority",
  federal_application: "Apply at the federal authority",
  consultation_with_lawyer: "Consult a lawyer",
};

/** Inline ring gauge for the confidence percentage. SVG-only so it
 *  prints crisply and degrades on legacy email clients. */
function ConfidenceRing({ pct, color }: { pct: number; color: string }) {
  const r = 18;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - pct / 100);
  return (
    <svg viewBox="0 0 44 44" className="h-11 w-11" aria-hidden>
      <circle
        cx="22"
        cy="22"
        r={r}
        fill="none"
        stroke="#e5e7eb"
        strokeWidth="4"
      />
      <circle
        cx="22"
        cy="22"
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="4"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={offset}
        transform="rotate(-90 22 22)"
      />
    </svg>
  );
}

export function BenefitCard({ benefit: b }: { benefit: Benefit }) {
  const [agentBadgeDismissed, setAgentBadgeDismissed] = useState(false);
  const tone = confidenceTone(b.confidence);
  const pct = Math.round(b.confidence * 100);
  const categoryLabel = CATEGORY_LABELS[b.category] ?? b.category;
  const categoryTone =
    CATEGORY_TONES[b.category] ?? "bg-gray-50 text-gray-700 ring-gray-200";

  return (
    <article
      className="slaw-card group relative overflow-hidden rounded-xl border border-[var(--slaw-line)] bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-12px_rgba(15,23,42,0.08)] transition-shadow hover:shadow-[0_2px_4px_rgba(15,23,42,0.06),0_16px_32px_-12px_rgba(15,23,42,0.12)]"
    >
      {/* Header — category chip + title + confidence gauge */}
      <header className="flex items-start justify-between gap-4 px-6 pb-4 pt-5 sm:px-7">
        <div className="min-w-0 flex-1">
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ring-1 ring-inset ${categoryTone}`}
          >
            {categoryLabel}
          </span>
          <h2 className="mt-2 text-xl font-semibold leading-snug text-[var(--slaw-ink)] sm:text-[1.35rem]">
            {b.title}
          </h2>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <div
            className={`flex items-center gap-2 rounded-lg ${tone.bg} px-2.5 py-1.5`}
            title={`${tone.label} (${pct}%)`}
          >
            <ConfidenceRing pct={pct} color={tone.ring} />
            <div className="flex flex-col leading-tight">
              <span className={`text-base font-semibold ${tone.text}`}>
                {pct}%
              </span>
              <span className={`text-[10px] font-semibold uppercase tracking-wide ${tone.text}`}>
                {tone.label.split(" ")[0]}
              </span>
            </div>
          </div>

          {!b.agent_provenance?.agent_backed && !agentBadgeDismissed && (
            <span
              tabIndex={0}
              role="status"
              aria-label={
                b.agent_provenance
                  ? `Unverified by agent. Verified via ${b.agent_provenance.call_kind}; no managed-agent tool use observed.`
                  : "Unverified by agent. No provenance recorded for this analysis."
              }
              title={
                b.agent_provenance
                  ? `Verified via ${b.agent_provenance.call_kind}; no managed-agent tool use observed.`
                  : "No provenance recorded for this analysis."
              }
              className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800 outline-none focus-visible:ring-2 focus-visible:ring-amber-400 slaw-no-print"
            >
              <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none" aria-hidden>
                <path d="M6 1.5v3.75M6 8.25v.75" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" />
                <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1" />
              </svg>
              Unverified by agent
              <button
                type="button"
                aria-label="Dismiss unverified-by-agent notice"
                onClick={() => setAgentBadgeDismissed(true)}
                className="ml-0.5 rounded-full px-1 leading-none text-amber-700 hover:bg-amber-100 hover:text-amber-900"
              >
                ×
              </button>
            </span>
          )}
        </div>
      </header>

      {/* Metadata strip — value + deadline. Print-friendly. */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-y border-dashed border-[var(--slaw-line)] bg-[var(--slaw-bg-elev)] px-6 py-3 text-sm sm:px-7">
        <div>
          <span className="text-[11px] font-medium uppercase tracking-wider text-[var(--slaw-ink-muted)]">
            Estimated value
          </span>
          <div className="font-semibold text-[var(--slaw-ink)]">
            CHF {b.estimated_value_chf.min.toLocaleString()}
            <span className="mx-1 text-[var(--slaw-ink-muted)]">–</span>
            {b.estimated_value_chf.max.toLocaleString()}
            <span className="ml-1 text-xs font-normal text-[var(--slaw-ink-muted)]">
              / {b.estimated_value_chf.per}
            </span>
          </div>
        </div>
        {b.time_limit_days && (
          <div className="rounded-md bg-orange-50 px-2.5 py-1 ring-1 ring-inset ring-orange-200">
            <span className="text-[11px] font-medium uppercase tracking-wider text-orange-700">
              Deadline
            </span>
            <div className="text-sm font-semibold text-orange-800">
              {b.time_limit_days} days
            </div>
          </div>
        )}
      </div>

      {/* Action band — promoted CTA-style, the answer to "what do I do next?" */}
      <div className="px-6 pt-5 sm:px-7">
        <div className="flex items-center gap-3 rounded-lg bg-[var(--slaw-primary-soft)] px-4 py-3 ring-1 ring-inset ring-emerald-200">
          <svg className="h-5 w-5 shrink-0 text-[var(--slaw-primary-strong)]" viewBox="0 0 20 20" fill="none" aria-hidden>
            <path d="M4 10l4 4 8-9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--slaw-primary-strong)] opacity-80">
              Next action
            </div>
            <div className="text-sm font-semibold leading-snug text-[var(--slaw-primary-strong)]">
              {ACTION_LABELS[b.required_action] ?? b.required_action}
            </div>
          </div>
        </div>
      </div>

      {/* Why this applies + Analysis */}
      {(b.evidence.length > 0 || b.llm_reasoning) && (
        <div className="grid gap-4 px-6 pt-5 sm:px-7 sm:grid-cols-5">
          {b.evidence.length > 0 && (
            <div className="sm:col-span-2">
              <p className="text-[11px] font-medium uppercase tracking-wider text-[var(--slaw-ink-muted)]">
                Why this applies
              </p>
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {b.evidence.map((ev, i) => (
                  <li
                    key={i}
                    className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-700 ring-1 ring-inset ring-slate-200"
                  >
                    <span className="font-medium text-slate-500">{ev.field}:</span>{" "}
                    {String(ev.value)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {b.llm_reasoning && (
            <div className="sm:col-span-3">
              <p className="text-[11px] font-medium uppercase tracking-wider text-[var(--slaw-ink-muted)]">
                Analysis
              </p>
              <p className="mt-2 text-sm leading-relaxed text-[var(--slaw-ink-soft)]">
                {b.llm_reasoning}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Legal basis — typeset like a citation block */}
      {b.citations.length > 0 && (
        <div className="mt-5 border-t border-[var(--slaw-line)] bg-[var(--slaw-bg-elev)] px-6 py-4 sm:px-7">
          <p className="text-[11px] font-medium uppercase tracking-wider text-[var(--slaw-ink-muted)]">
            Legal basis
          </p>
          <ul className="mt-2 space-y-2">
            {b.citations.map((c, i) => (
              <li
                key={i}
                className="border-l-2 border-[var(--slaw-accent)] pl-3 text-sm leading-relaxed text-[var(--slaw-ink)]"
              >
                <span className="slaw-citation font-semibold text-[var(--slaw-accent)]">
                  SR&nbsp;{c.sr_number} · Art.&nbsp;{c.article}
                </span>
                {c.quote_under_15_words && (
                  <span className="mt-0.5 block text-[var(--slaw-ink-soft)] italic">
                    &ldquo;{c.quote_under_15_words}&rdquo;
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Supporting doctrine — collapsed, advisory */}
      {b.supporting_doctrine && b.supporting_doctrine.length > 0 && (
        <details className="group/det border-t border-[var(--slaw-line)] px-6 py-3 sm:px-7">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-[11px] font-medium uppercase tracking-wider text-[var(--slaw-ink-muted)] hover:text-[var(--slaw-ink)]">
            <span className="flex items-center gap-1.5">
              <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none" aria-hidden>
                <path d="M2 4h8M2 6h8M2 8h5" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" />
              </svg>
              Supporting doctrine ({b.supporting_doctrine.length})
              <span className="font-normal normal-case text-[var(--slaw-ink-muted)] opacity-70">
                — advisory only
              </span>
            </span>
            <span className="text-[var(--slaw-ink-muted)] transition-transform group-open/det:rotate-180">
              ▾
            </span>
          </summary>
          <p className="mt-2 text-xs italic text-[var(--slaw-ink-muted)]">
            Background context from Swiss legal commentary. Not binding
            authority — the Legal basis citations above remain the sole source.
          </p>
          <ul className="mt-2 space-y-1.5">
            {b.supporting_doctrine.map((d, i) => (
              <li key={i} className="text-sm text-[var(--slaw-ink-soft)]">
                <span className="font-medium text-[var(--slaw-ink)]">{d.source_doc}</span>
                {d.chapter && (
                  <span className="text-[var(--slaw-ink-muted)]"> — {d.chapter}</span>
                )}
                <span className="ml-2 text-[11px] text-[var(--slaw-ink-muted)]">
                  similarity {Math.round((d.score ?? 0) * 100)}%
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Disclaimer + follow-up affordance */}
      <div className="border-t border-[var(--slaw-line)] px-6 py-4 sm:px-7">
        <p className="text-xs italic text-[var(--slaw-ink-muted)]">
          {b.disclaimer}
        </p>
        <div className="slaw-no-print mt-2">
          <AskFollowUp benefitId={b.entitlement_id} />
        </div>
      </div>
    </article>
  );
}
