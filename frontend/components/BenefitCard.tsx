import type { Benefit } from "@/lib/api-client";
import { AskFollowUp } from "./AskFollowUp";

function confidenceColor(c: number): string {
  if (c >= 0.85) return "text-emerald-700 bg-emerald-50";
  if (c >= 0.7) return "text-yellow-700 bg-yellow-50";
  return "text-orange-700 bg-orange-50";
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

const ACTION_LABELS: Record<string, string> = {
  claim_letter_to_landlord: "Send letter to landlord",
  tax_declaration_field: "Enter in tax declaration",
  employer_request: "Request from employer",
  cantonal_application: "Apply at cantonal authority",
  federal_application: "Apply at federal authority",
  consultation_with_lawyer: "Consult a lawyer",
};

export function BenefitCard({ benefit: b }: { benefit: Benefit }) {
  return (
    <article className="rounded-lg border bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <span className="text-xs font-medium uppercase tracking-wide text-gray-400">
            {CATEGORY_LABELS[b.category] ?? b.category}
          </span>
          <h2 className="mt-1 text-xl font-semibold text-gray-900">{b.title}</h2>
        </div>
        <span className={`rounded-full px-3 py-1 text-sm font-semibold ${confidenceColor(b.confidence)}`}>
          {Math.round(b.confidence * 100)}% confidence
        </span>
      </div>

      <div className="mt-3 flex items-center gap-4 text-sm text-gray-600">
        <span>
          Estimated value:{" "}
          <strong>
            CHF {b.estimated_value_chf.min.toLocaleString()}–
            {b.estimated_value_chf.max.toLocaleString()} / {b.estimated_value_chf.per}
          </strong>
        </span>
        {b.time_limit_days && (
          <span className="text-orange-600">
            Deadline: {b.time_limit_days} days
          </span>
        )}
      </div>

      {b.citations.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-400">Legal basis</p>
          <ul className="mt-1 space-y-1">
            {b.citations.map((c, i) => (
              <li key={i} className="text-sm text-gray-700">
                <span className="font-medium">SR {c.sr_number} Art. {c.article}</span>
                {c.quote_under_15_words && (
                  <span className="ml-2 text-gray-500 italic">&ldquo;{c.quote_under_15_words}&rdquo;</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {b.evidence.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-400">Why this applies to you</p>
          <ul className="mt-1 flex flex-wrap gap-2">
            {b.evidence.map((ev, i) => (
              <li key={i} className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                {ev.field}: {String(ev.value)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {b.llm_reasoning && (
        <div className="mt-3 rounded bg-gray-50 px-3 py-2 text-sm text-gray-600">
          <span className="font-medium text-gray-700">Analysis: </span>
          {b.llm_reasoning}
        </div>
      )}

      {b.supporting_doctrine && b.supporting_doctrine.length > 0 && (
        <details className="mt-3 rounded border border-dashed border-indigo-200 bg-indigo-50/40 px-3 py-2 text-sm text-gray-700">
          <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-indigo-700">
            Why this applies (advisory doctrine)
          </summary>
          <p className="mt-1 text-xs italic text-indigo-900/70">
            Background context from Swiss legal commentary. Not binding authority — the
            <span className="font-medium"> Legal basis</span> citations above remain the
            sole source of authority.
          </p>
          <ul className="mt-2 space-y-1">
            {b.supporting_doctrine.map((d, i) => (
              <li key={i} className="text-sm text-gray-700">
                <span className="font-medium">{d.source_doc}</span>
                {d.chapter && <span className="text-gray-500"> — {d.chapter}</span>}
                <span className="ml-2 text-xs text-gray-400">
                  similarity {Math.round(d.score * 100)}%
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="mt-4 flex items-center gap-3">
        <span className="rounded border border-emerald-200 bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-800">
          Action: {ACTION_LABELS[b.required_action] ?? b.required_action}
        </span>
      </div>

      <p className="mt-2 text-xs text-gray-400 italic">{b.disclaimer}</p>

      <AskFollowUp benefitId={b.entitlement_id} />
    </article>
  );
}
