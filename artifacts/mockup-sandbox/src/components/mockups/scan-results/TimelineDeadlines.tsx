import React, { useMemo } from "react";
import { motion } from "framer-motion";
import {
  AlarmClock,
  CalendarDays,
  Clock,
  Infinity as InfinityIcon,
  ChevronRight,
} from "lucide-react";
import "./_group.css";
import {
  ACTION_LABELS,
  CATEGORY_LABELS,
  formatChf,
  midpointValue,
  type Benefit,
} from "./types";
import { MOCK_REPORT } from "./mockReport";

/**
 * TimelineDeadlines — time-based view organized by urgency.
 *
 * Hypothesis: The job-to-be-done is "what should I act on this week vs. this
 * year vs. whenever I get to it?" A vertical timeline with date markers makes
 * the deadlines visceral. Tax-window items cluster around March, tenancy
 * items have hard 30-day windows, employment items are open-ended.
 */

type Bucket = "this_week" | "this_month" | "this_quarter" | "this_year" | "anytime";

const BUCKET_ORDER: Bucket[] = [
  "this_week",
  "this_month",
  "this_quarter",
  "this_year",
  "anytime",
];

const BUCKET_LABELS: Record<Bucket, string> = {
  this_week:    "This week",
  this_month:   "Next 30 days",
  this_quarter: "Next 90 days",
  this_year:    "By end of year",
  anytime:      "No deadline",
};

const BUCKET_COPY: Record<Bucket, string> = {
  this_week:    "Hard deadlines — act now or you lose the right.",
  this_month:   "Statutory windows close inside a month.",
  this_quarter: "Plan a deliberate hour for these.",
  this_year:    "Tax-cycle items — fold them into your annual filing.",
  anytime:      "Open-ended rights you can claim whenever.",
};

const BUCKET_ACCENTS: Record<Bucket, { dot: string; ring: string; text: string; bar: string }> = {
  this_week:    { dot: "bg-rose-600",    ring: "ring-rose-200",   text: "text-rose-700",    bar: "bg-rose-200" },
  this_month:   { dot: "bg-amber-600",   ring: "ring-amber-200",  text: "text-amber-700",   bar: "bg-amber-200" },
  this_quarter: { dot: "bg-yellow-500",  ring: "ring-yellow-200", text: "text-yellow-700",  bar: "bg-yellow-200" },
  this_year:    { dot: "bg-emerald-700", ring: "ring-emerald-200",text: "text-emerald-800", bar: "bg-emerald-200" },
  anytime:      { dot: "bg-slate-400",   ring: "ring-slate-200",  text: "text-slate-600",   bar: "bg-slate-200" },
};

function bucketOf(b: Benefit): Bucket {
  const days = b.time_limit_days;
  if (days == null) return "anytime";
  if (days <= 7)   return "this_week";
  if (days <= 30)  return "this_month";
  if (days <= 90)  return "this_quarter";
  if (days <= 365) return "this_year";
  return "anytime";
}

function deadlineLabel(days: number | null | undefined, generatedAt: string): string {
  if (days == null) return "No statutory deadline";
  const start = new Date(generatedAt);
  const due = new Date(start.getTime() + days * 24 * 60 * 60 * 1000);
  return due.toLocaleDateString("en-CH", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export default function TimelineDeadlines() {
  const buckets = useMemo(() => {
    const map = new Map<Bucket, Benefit[]>();
    for (const b of MOCK_REPORT.benefits) {
      const k = bucketOf(b);
      const arr = map.get(k) ?? [];
      arr.push(b);
      map.set(k, arr);
    }
    for (const [k, arr] of map.entries()) {
      arr.sort((a, b) => (a.time_limit_days ?? 9999) - (b.time_limit_days ?? 9999));
      map.set(k, arr);
    }
    return BUCKET_ORDER.filter((b) => map.has(b)).map((b) => ({
      bucket: b,
      benefits: map.get(b)!,
    }));
  }, []);

  const urgent = buckets
    .filter((g) => g.bucket === "this_week" || g.bucket === "this_month")
    .reduce((acc, g) => acc + g.benefits.length, 0);

  return (
    <div className="slaw-results min-h-screen bg-[var(--slaw-bg)] antialiased">
      {/* Header */}
      <header className="border-b border-[var(--slaw-line)] bg-[var(--slaw-card)]">
        <div className="mx-auto max-w-3xl px-6 pt-10 pb-8">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2 text-[var(--slaw-primary-strong)]">
              <AlarmClock className="h-4 w-4" />
              <span className="text-xs font-semibold uppercase tracking-[0.18em]">
                Slaw · Action Calendar
              </span>
            </div>
            <span className="text-xs text-[var(--slaw-ink-mute)]">
              {new Date(MOCK_REPORT.generated_at).toLocaleDateString("en-CH", {
                dateStyle: "medium",
              })}
            </span>
          </div>

          <h1 className="text-3xl font-semibold tracking-tight text-[var(--slaw-ink)]">
            Your rights, on a calendar
          </h1>
          <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-[var(--slaw-ink-soft)]">
            Some entitlements expire if you don’t claim them in time. Walk down
            the timeline; deal with the red dots first.
          </p>

          {urgent > 0 && (
            <div className="mt-5 flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-[13px]">
              <span className="flex h-1.5 w-1.5 flex-none rounded-full bg-rose-600 ring-2 ring-rose-200 ring-offset-1 animate-pulse" />
              <span className="text-rose-800">
                <span className="font-semibold">{urgent}</span>{" "}
                {urgent === 1 ? "item has" : "items have"} a deadline within the next
                30 days.
              </span>
            </div>
          )}
        </div>
      </header>

      {/* Timeline */}
      <main className="mx-auto max-w-3xl px-6 py-10">
        <div className="relative">
          {/* Spine */}
          <div
            className="absolute left-[15px] top-2 bottom-2 w-px bg-gradient-to-b from-[var(--slaw-line-strong)] via-[var(--slaw-line)] to-transparent"
            aria-hidden
          />

          <div className="space-y-12">
            {buckets.map((group, gi) => {
              const accent = BUCKET_ACCENTS[group.bucket];
              return (
                <motion.section
                  key={group.bucket}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.25, delay: gi * 0.05 }}
                  className="relative pl-12"
                >
                  {/* Marker */}
                  <div className="absolute left-0 top-1.5 flex items-center justify-center">
                    <div
                      className={`h-[14px] w-[14px] rounded-full ${accent.dot} ring-4 ring-white shadow-sm ring-offset-0`}
                    />
                    <div className={`absolute h-7 w-7 rounded-full ring-1 ring-inset ${accent.ring}`} />
                  </div>

                  {/* Bucket header */}
                  <div className="flex items-baseline justify-between gap-3">
                    <h2 className={`text-[15px] font-semibold tracking-tight ${accent.text}`}>
                      {BUCKET_LABELS[group.bucket]}
                    </h2>
                    <span className="text-[11px] font-medium tabular-nums text-[var(--slaw-ink-mute)]">
                      {group.benefits.length}{" "}
                      {group.benefits.length === 1 ? "item" : "items"}
                    </span>
                  </div>
                  <p className="mt-0.5 text-[12.5px] text-[var(--slaw-ink-mute)]">
                    {BUCKET_COPY[group.bucket]}
                  </p>

                  {/* Items */}
                  <ul className="mt-4 space-y-3">
                    {group.benefits.map((b) => (
                      <TimelineItem key={b.entitlement_id} benefit={b} accentBar={accent.bar} />
                    ))}
                  </ul>
                </motion.section>
              );
            })}
          </div>
        </div>

        <p className="mt-12 text-center text-[11px] leading-relaxed text-[var(--slaw-ink-mute)]">
          Not a substitute for advice from a Swiss attorney registered with a
          cantonal bar.
        </p>
      </main>
    </div>
  );
}

function TimelineItem({
  benefit,
  accentBar,
}: {
  benefit: Benefit;
  accentBar: string;
}) {
  const value = benefit.estimated_value_chf;
  const perLabel = value.per === "year" ? "/ year" : value.per === "month" ? "/ month" : "one-time";
  const due = deadlineLabel(benefit.time_limit_days, MOCK_REPORT.generated_at);

  return (
    <li className="group relative overflow-hidden rounded-lg border border-[var(--slaw-line)] bg-[var(--slaw-card)] shadow-sm transition-shadow hover:shadow-md">
      <div className={`absolute left-0 top-0 bottom-0 w-1 ${accentBar}`} />
      <div className="flex items-start gap-4 px-5 py-4 pl-6">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--slaw-ink-mute)]">
            <span>{CATEGORY_LABELS[benefit.category]}</span>
            <span className="text-[var(--slaw-line-strong)]">·</span>
            <span className="inline-flex items-center gap-1">
              {benefit.time_limit_days == null ? (
                <InfinityIcon className="h-3 w-3" />
              ) : (
                <Clock className="h-3 w-3" />
              )}
              {benefit.time_limit_days == null
                ? "Open-ended"
                : `${benefit.time_limit_days} days from scan`}
            </span>
          </div>
          <h3 className="mt-1 text-[15px] font-semibold text-[var(--slaw-ink)]">
            {benefit.title}
          </h3>
          <p className="mt-1.5 line-clamp-2 text-[13px] leading-relaxed text-[var(--slaw-ink-soft)]">
            {benefit.llm_reasoning}
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-[var(--slaw-ink-mute)]">
            <span className="inline-flex items-center gap-1">
              <CalendarDays className="h-3 w-3" />
              <span className="text-[var(--slaw-ink-soft)]">
                {benefit.time_limit_days == null ? "Anytime" : `Due ${due}`}
              </span>
            </span>
            <span>·</span>
            <span className="tabular-nums text-[var(--slaw-ink-soft)]">
              CHF {formatChf(value.min)}–{formatChf(value.max)} {perLabel}
            </span>
            <span>·</span>
            <span>{Math.round(benefit.confidence * 100)}% conf.</span>
          </div>
        </div>

        <div className="flex flex-none flex-col items-end gap-2">
          <div className="text-right">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--slaw-ink-mute)]">
              Midpoint
            </div>
            <div className="tabular-nums text-[15px] font-semibold text-[var(--slaw-primary-strong)]">
              CHF {formatChf(midpointValue(value))}
            </div>
          </div>
          <button className="inline-flex items-center gap-1 rounded-md border border-[var(--slaw-line)] bg-white px-2.5 py-1.5 text-[12px] font-medium text-[var(--slaw-ink)] hover:border-[var(--slaw-primary)] hover:text-[var(--slaw-primary-strong)] transition-colors">
            {ACTION_LABELS[benefit.required_action]}
            <ChevronRight className="h-3 w-3" />
          </button>
        </div>
      </div>
    </li>
  );
}
