import React, { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight,
  ChevronDown,
  Clock,
  ScanSearch,
  TrendingUp,
  Sparkles,
  CheckCircle2,
} from "lucide-react";
import "./_group.css";
import {
  ACTION_LABELS,
  CATEGORY_LABELS,
  formatChf,
  impactScore,
  midpointValue,
  type Benefit,
} from "./types";
import { MOCK_REPORT } from "./mockReport";

/**
 * PrioritizedList — single ranked list ordered by impact (CHF value × confidence).
 *
 * Hypothesis: Luis doesn't want categories or filters. He wants to know what to
 * do first. The page reads like a focused weekly to-do list: rank, title,
 * money on the right, one expandable card for the why and the action.
 */
export default function PrioritizedList() {
  const ranked = useMemo(() => {
    return [...MOCK_REPORT.benefits].sort(
      (a, b) => impactScore(b) - impactScore(a),
    );
  }, []);

  const [openId, setOpenId] = useState<string | null>(ranked[0]?.entitlement_id ?? null);

  const totalLow = ranked.reduce(
    (acc, b) => acc + b.estimated_value_chf.min,
    0,
  );
  const totalHigh = ranked.reduce(
    (acc, b) => acc + b.estimated_value_chf.max,
    0,
  );
  const topImpact = ranked[0] ? midpointValue(ranked[0].estimated_value_chf) : 0;

  return (
    <div className="slaw-results min-h-screen bg-[var(--slaw-bg)] antialiased">
      {/* Header */}
      <header className="border-b border-[var(--slaw-line)] bg-[var(--slaw-card)]">
        <div className="mx-auto max-w-3xl px-6 pt-10 pb-8">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2 text-[var(--slaw-primary-strong)]">
              <ScanSearch className="h-4 w-4" />
              <span className="text-xs font-semibold uppercase tracking-[0.18em]">
                Slaw · Rights Scan
              </span>
            </div>
            <span className="text-xs text-[var(--slaw-ink-mute)]">
              {new Date(MOCK_REPORT.generated_at).toLocaleDateString("en-CH", {
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </span>
          </div>

          <h1 className="text-3xl font-semibold tracking-tight text-[var(--slaw-ink)]">
            Your top {ranked.length} actions, ranked by impact
          </h1>
          <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-[var(--slaw-ink-soft)]">
            Tackle them in this order. Each item is weighted by the money on the
            table and how confident we are that it applies to you.
          </p>

          {/* Summary strip */}
          <div className="mt-7 grid grid-cols-3 gap-3">
            <SummaryStat
              icon={<TrendingUp className="h-4 w-4" />}
              label="Estimated total"
              value={`CHF ${formatChf(totalLow)}–${formatChf(totalHigh)}`}
              accent
            />
            <SummaryStat
              icon={<Sparkles className="h-4 w-4" />}
              label="Highest single item"
              value={`CHF ${formatChf(topImpact)}`}
            />
            <SummaryStat
              icon={<CheckCircle2 className="h-4 w-4" />}
              label="Items found"
              value={`${ranked.length} (+${MOCK_REPORT.suppressed_count} low conf.)`}
            />
          </div>
        </div>
      </header>

      {/* Ranked list */}
      <main className="mx-auto max-w-3xl px-6 py-8">
        <ol className="space-y-3">
          {ranked.map((b, idx) => {
            const isOpen = openId === b.entitlement_id;
            return (
              <RankedRow
                key={b.entitlement_id}
                rank={idx + 1}
                benefit={b}
                isOpen={isOpen}
                onToggle={() =>
                  setOpenId((prev) =>
                    prev === b.entitlement_id ? null : b.entitlement_id,
                  )
                }
              />
            );
          })}
        </ol>

        <p className="mt-10 text-center text-[11px] leading-relaxed text-[var(--slaw-ink-mute)]">
          Not a substitute for advice from a Swiss attorney registered with a
          cantonal bar.
        </p>
      </main>
    </div>
  );
}

function SummaryStat({
  icon,
  label,
  value,
  accent = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border px-4 py-3 ${
        accent
          ? "border-[var(--slaw-primary)]/20 bg-[var(--slaw-primary-soft)]"
          : "border-[var(--slaw-line)] bg-[var(--slaw-bg)]"
      }`}
    >
      <div
        className={`flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider ${
          accent ? "text-[var(--slaw-primary-strong)]" : "text-[var(--slaw-ink-mute)]"
        }`}
      >
        {icon}
        {label}
      </div>
      <div
        className={`mt-1 text-base font-semibold tabular-nums ${
          accent ? "text-[var(--slaw-primary-strong)]" : "text-[var(--slaw-ink)]"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function RankedRow({
  rank,
  benefit,
  isOpen,
  onToggle,
}: {
  rank: number;
  benefit: Benefit;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const value = benefit.estimated_value_chf;
  const perLabel =
    value.per === "year" ? "/ year" : value.per === "month" ? "/ month" : "one-time";

  return (
    <li>
      <article
        className={`group rounded-xl border bg-[var(--slaw-card)] transition-shadow ${
          isOpen
            ? "border-[var(--slaw-primary)]/40 shadow-[0_4px_16px_-4px_rgba(4,120,87,0.15)]"
            : "border-[var(--slaw-line)] hover:border-[var(--slaw-line-strong)] hover:shadow-sm"
        }`}
      >
        <button
          onClick={onToggle}
          className="flex w-full items-center gap-5 px-5 py-4 text-left"
        >
          {/* Rank */}
          <div className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-[var(--slaw-bg)] text-sm font-semibold tabular-nums text-[var(--slaw-ink-soft)] ring-1 ring-inset ring-[var(--slaw-line)]">
            {rank}
          </div>

          {/* Title + meta */}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-[var(--slaw-ink-mute)]">
              <span>{CATEGORY_LABELS[benefit.category]}</span>
              {benefit.time_limit_days && benefit.time_limit_days <= 60 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-[var(--slaw-warn-bg)] px-2 py-0.5 text-[10px] font-semibold text-[var(--slaw-warn)]">
                  <Clock className="h-2.5 w-2.5" />
                  {benefit.time_limit_days} days
                </span>
              )}
            </div>
            <h2 className="mt-0.5 truncate text-[15px] font-semibold text-[var(--slaw-ink)]">
              {benefit.title}
            </h2>
          </div>

          {/* Value */}
          <div className="flex flex-none flex-col items-end">
            <div className="text-base font-semibold tabular-nums text-[var(--slaw-primary-strong)]">
              CHF {formatChf(value.min)}–{formatChf(value.max)}
            </div>
            <div className="text-[11px] text-[var(--slaw-ink-mute)]">{perLabel}</div>
          </div>

          {/* Confidence + chevron */}
          <div className="flex flex-none items-center gap-3">
            <ConfidenceMeter value={benefit.confidence} />
            <ChevronDown
              className={`h-4 w-4 text-[var(--slaw-ink-mute)] transition-transform ${
                isOpen ? "rotate-180" : ""
              }`}
            />
          </div>
        </button>

        <AnimatePresence initial={false}>
          {isOpen && (
            <motion.div
              key="content"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.22, ease: [0.32, 0.72, 0.45, 1] }}
              className="overflow-hidden"
            >
              <div className="border-t border-[var(--slaw-line)] px-5 py-4">
                <p className="text-[14px] leading-relaxed text-[var(--slaw-ink-soft)]">
                  {benefit.llm_reasoning}
                </p>

                <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3">
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--slaw-ink-mute)]">
                      Legal basis
                    </div>
                    <ul className="mt-1.5 space-y-1.5">
                      {benefit.citations.map((c, i) => (
                        <li key={i} className="text-[12.5px] text-[var(--slaw-ink-soft)]">
                          <span className="font-semibold text-[var(--slaw-ink)]">
                            SR {c.sr_number}
                          </span>{" "}
                          Art. {c.article}
                          {c.paragraph && ` ¶${c.paragraph}`}
                          <div className="mt-0.5 italic text-[var(--slaw-ink-mute)]">
                            “{c.quote_under_15_words}”
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--slaw-ink-mute)]">
                      Why this applies to you
                    </div>
                    <ul className="mt-1.5 flex flex-wrap gap-1.5">
                      {benefit.evidence.map((e, i) => (
                        <li
                          key={i}
                          className="rounded-md bg-[var(--slaw-bg)] px-2 py-1 text-[11px] text-[var(--slaw-ink-soft)] ring-1 ring-inset ring-[var(--slaw-line)]"
                        >
                          <span className="font-medium text-[var(--slaw-ink)]">
                            {e.field}
                          </span>
                          : {String(e.value)}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div className="mt-5 flex items-center justify-between">
                  <span className="text-[11px] text-[var(--slaw-ink-mute)]">
                    Confidence {Math.round(benefit.confidence * 100)}%
                  </span>
                  <button className="inline-flex items-center gap-1.5 rounded-md bg-[var(--slaw-primary)] px-3.5 py-2 text-[13px] font-semibold text-white shadow-sm hover:bg-[var(--slaw-primary-strong)] transition-colors">
                    {ACTION_LABELS[benefit.required_action]}
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </article>
    </li>
  );
}

function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    value >= 0.85
      ? "var(--slaw-primary)"
      : value >= 0.7
        ? "#ca8a04"
        : "#ea580c";
  return (
    <div
      className="flex h-7 items-center gap-1.5 rounded-full bg-[var(--slaw-bg)] px-2.5 ring-1 ring-inset ring-[var(--slaw-line)]"
      title={`Confidence ${pct}%`}
    >
      <div className="flex h-1.5 w-10 overflow-hidden rounded-full bg-[var(--slaw-line)]">
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-[11px] font-medium tabular-nums text-[var(--slaw-ink-soft)]">
        {pct}%
      </span>
    </div>
  );
}
