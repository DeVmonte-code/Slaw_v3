import React, { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Banknote,
  Briefcase,
  Building,
  Heart,
  Landmark,
  Scale,
  ShieldCheck,
  ChevronRight,
  Filter,
} from "lucide-react";
import "./_group.css";
import {
  ACTION_LABELS,
  CATEGORY_LABELS,
  formatChf,
  midpointValue,
  type Benefit,
  type BenefitCategory,
} from "./types";
import { MOCK_REPORT } from "./mockReport";

/**
 * CategoryCards — grouped, scannable dashboard.
 *
 * Hypothesis: Luis wants to see his rights as a complete portfolio: tax over
 * here, tenancy over there, employment in another column. He scans the totals
 * by domain first, then opens whichever bucket he wants to act on. A
 * dashboard for the legally entitled.
 */

const CATEGORY_ICONS: Record<BenefitCategory, React.ComponentType<{ className?: string }>> = {
  tax_deduction: Banknote,
  tenancy_right: Building,
  employment_right: Briefcase,
  family_benefit: Heart,
  business_subsidy: Landmark,
  social_security: ShieldCheck,
  consumer_protection: Scale,
};

const CATEGORY_THEMES: Record<BenefitCategory, { tint: string; ink: string; ring: string }> = {
  tax_deduction:        { tint: "bg-emerald-50",  ink: "text-emerald-800", ring: "ring-emerald-200" },
  tenancy_right:        { tint: "bg-sky-50",      ink: "text-sky-800",     ring: "ring-sky-200" },
  employment_right:     { tint: "bg-amber-50",    ink: "text-amber-800",   ring: "ring-amber-200" },
  family_benefit:       { tint: "bg-rose-50",     ink: "text-rose-800",    ring: "ring-rose-200" },
  business_subsidy:     { tint: "bg-violet-50",   ink: "text-violet-800",  ring: "ring-violet-200" },
  social_security:      { tint: "bg-teal-50",     ink: "text-teal-800",    ring: "ring-teal-200" },
  consumer_protection:  { tint: "bg-slate-100",   ink: "text-slate-800",   ring: "ring-slate-200" },
};

interface CategoryGroup {
  category: BenefitCategory;
  benefits: Benefit[];
  totalLow: number;
  totalHigh: number;
  topConfidence: number;
}

export default function CategoryCards() {
  const groups: CategoryGroup[] = useMemo(() => {
    const map = new Map<BenefitCategory, Benefit[]>();
    for (const b of MOCK_REPORT.benefits) {
      const arr = map.get(b.category) ?? [];
      arr.push(b);
      map.set(b.category, arr);
    }
    const result: CategoryGroup[] = [];
    for (const [category, benefits] of map.entries()) {
      const sorted = [...benefits].sort((a, b) => b.confidence - a.confidence);
      result.push({
        category,
        benefits: sorted,
        totalLow: sorted.reduce((acc, b) => acc + b.estimated_value_chf.min, 0),
        totalHigh: sorted.reduce((acc, b) => acc + b.estimated_value_chf.max, 0),
        topConfidence: Math.max(...sorted.map((b) => b.confidence)),
      });
    }
    return result.sort((a, b) => b.totalHigh - a.totalHigh);
  }, []);

  const [filter, setFilter] = useState<BenefitCategory | "all">("all");
  const visible = filter === "all" ? groups : groups.filter((g) => g.category === filter);

  const grandTotalLow = groups.reduce((a, g) => a + g.totalLow, 0);
  const grandTotalHigh = groups.reduce((a, g) => a + g.totalHigh, 0);

  return (
    <div className="slaw-results min-h-screen bg-[var(--slaw-bg)] antialiased">
      {/* Header */}
      <header className="border-b border-[var(--slaw-line)] bg-[var(--slaw-card)]">
        <div className="mx-auto max-w-5xl px-6 pt-10 pb-7">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-[var(--slaw-primary)]">
                <Scale className="h-3.5 w-3.5 text-white" />
              </div>
              <span className="text-sm font-semibold tracking-tight text-[var(--slaw-primary-strong)]">
                Slaw
              </span>
            </div>
            <span className="text-xs text-[var(--slaw-ink-mute)]">
              Generated{" "}
              {new Date(MOCK_REPORT.generated_at).toLocaleString("en-CH", {
                dateStyle: "medium",
                timeStyle: "short",
              })}
            </span>
          </div>

          <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="text-[28px] font-semibold tracking-tight text-[var(--slaw-ink)]">
                Your rights, organized by domain
              </h1>
              <p className="mt-1 text-[14px] text-[var(--slaw-ink-soft)]">
                {MOCK_REPORT.benefits.length} entitlements across {groups.length}{" "}
                categories ·{" "}
                <span className="text-[var(--slaw-ink-mute)]">
                  {MOCK_REPORT.suppressed_count} suppressed below the confidence
                  threshold
                </span>
              </p>
            </div>
            <div className="rounded-xl border border-[var(--slaw-primary)]/20 bg-[var(--slaw-primary-soft)] px-5 py-4">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--slaw-primary-strong)]">
                Estimated total value
              </div>
              <div className="mt-0.5 text-2xl font-semibold tabular-nums text-[var(--slaw-primary-strong)]">
                CHF {formatChf(grandTotalLow)}–{formatChf(grandTotalHigh)}
              </div>
            </div>
          </div>

          {/* Filter chips */}
          <div className="mt-7 flex items-center gap-2">
            <Filter className="h-3.5 w-3.5 text-[var(--slaw-ink-mute)]" />
            <FilterChip active={filter === "all"} onClick={() => setFilter("all")}>
              All ({MOCK_REPORT.benefits.length})
            </FilterChip>
            {groups.map((g) => (
              <FilterChip
                key={g.category}
                active={filter === g.category}
                onClick={() => setFilter(g.category)}
              >
                {CATEGORY_LABELS[g.category]} ({g.benefits.length})
              </FilterChip>
            ))}
          </div>
        </div>
      </header>

      {/* Grid */}
      <main className="mx-auto max-w-5xl px-6 py-8">
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          {visible.map((group, gi) => {
            const Icon = CATEGORY_ICONS[group.category];
            const theme = CATEGORY_THEMES[group.category];
            return (
              <motion.section
                key={group.category}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, delay: gi * 0.04 }}
                className="flex flex-col rounded-xl border border-[var(--slaw-line)] bg-[var(--slaw-card)] shadow-sm"
              >
                {/* Header */}
                <div className="flex items-start justify-between gap-4 border-b border-[var(--slaw-line)] px-5 py-4">
                  <div className="flex items-start gap-3">
                    <div
                      className={`flex h-10 w-10 flex-none items-center justify-center rounded-lg ${theme.tint} ${theme.ink} ring-1 ring-inset ${theme.ring}`}
                    >
                      <Icon className="h-5 w-5" />
                    </div>
                    <div>
                      <h2 className="text-[15px] font-semibold text-[var(--slaw-ink)]">
                        {CATEGORY_LABELS[group.category]}
                      </h2>
                      <div className="mt-0.5 text-[12px] text-[var(--slaw-ink-mute)]">
                        {group.benefits.length}{" "}
                        {group.benefits.length === 1 ? "entitlement" : "entitlements"}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--slaw-ink-mute)]">
                      Range
                    </div>
                    <div className="text-[14px] font-semibold tabular-nums text-[var(--slaw-ink)]">
                      CHF {formatChf(group.totalLow)}–{formatChf(group.totalHigh)}
                    </div>
                  </div>
                </div>

                {/* Items */}
                <ul className="divide-y divide-[var(--slaw-line)]">
                  {group.benefits.map((b) => (
                    <CategoryItem key={b.entitlement_id} benefit={b} />
                  ))}
                </ul>
              </motion.section>
            );
          })}
        </div>

        <p className="mt-10 text-center text-[11px] leading-relaxed text-[var(--slaw-ink-mute)]">
          Not a substitute for advice from a Swiss attorney registered with a
          cantonal bar.
        </p>
      </main>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-[12px] font-medium transition-colors ${
        active
          ? "bg-[var(--slaw-ink)] text-white"
          : "bg-[var(--slaw-bg)] text-[var(--slaw-ink-soft)] ring-1 ring-inset ring-[var(--slaw-line)] hover:bg-white hover:text-[var(--slaw-ink)]"
      }`}
    >
      {children}
    </button>
  );
}

function CategoryItem({ benefit }: { benefit: Benefit }) {
  const [open, setOpen] = useState(false);
  const value = benefit.estimated_value_chf;
  const perLabel = value.per === "year" ? "/yr" : value.per === "month" ? "/mo" : "once";

  return (
    <li>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 px-5 py-3 text-left hover:bg-[var(--slaw-bg)] transition-colors"
      >
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14px] font-medium text-[var(--slaw-ink)]">
            {benefit.title}
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--slaw-ink-mute)]">
            <span className="tabular-nums">
              CHF {formatChf(midpointValue(value))} {perLabel}
            </span>
            <span>·</span>
            <span>{Math.round(benefit.confidence * 100)}% confidence</span>
            {benefit.time_limit_days && benefit.time_limit_days <= 60 && (
              <>
                <span>·</span>
                <span className="font-medium text-[var(--slaw-warn)]">
                  {benefit.time_limit_days}d window
                </span>
              </>
            )}
          </div>
        </div>
        <ChevronRight
          className={`h-4 w-4 flex-none text-[var(--slaw-ink-mute)] transition-transform ${
            open ? "rotate-90" : ""
          }`}
        />
      </button>

      {open && (
        <div className="border-t border-[var(--slaw-line)] bg-[var(--slaw-bg)]/60 px-5 py-3">
          <p className="text-[13px] leading-relaxed text-[var(--slaw-ink-soft)]">
            {benefit.llm_reasoning}
          </p>
          {benefit.citations[0] && (
            <div className="mt-2 text-[11px] text-[var(--slaw-ink-mute)]">
              <span className="font-semibold text-[var(--slaw-ink-soft)]">
                SR {benefit.citations[0].sr_number}
              </span>{" "}
              Art. {benefit.citations[0].article} —{" "}
              <span className="italic">
                “{benefit.citations[0].quote_under_15_words}”
              </span>
            </div>
          )}
          <button className="mt-3 inline-flex items-center gap-1 rounded-md border border-[var(--slaw-primary)]/30 bg-white px-2.5 py-1 text-[11px] font-medium text-[var(--slaw-primary-strong)] hover:bg-[var(--slaw-primary-soft)] transition-colors">
            {ACTION_LABELS[benefit.required_action]}
            <ChevronRight className="h-3 w-3" />
          </button>
        </div>
      )}
    </li>
  );
}
