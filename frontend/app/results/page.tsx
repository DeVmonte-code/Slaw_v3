"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { BenefitCard } from "@/components/BenefitCard";
import type { BenefitReport } from "@/lib/api-client";

function SkeletonCard() {
  return (
    <div className="rounded-xl border border-[var(--slaw-line)] bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 space-y-3">
          <div className="slaw-skeleton h-3 w-24" />
          <div className="slaw-skeleton h-5 w-3/4" />
        </div>
        <div className="slaw-skeleton h-11 w-20" />
      </div>
      <div className="mt-5 space-y-2">
        <div className="slaw-skeleton h-3 w-full" />
        <div className="slaw-skeleton h-3 w-5/6" />
        <div className="slaw-skeleton h-3 w-2/3" />
      </div>
    </div>
  );
}

function EmptyState({ onReset }: { onReset: () => void }) {
  return (
    <div className="rounded-2xl border border-dashed border-[var(--slaw-line-strong)] bg-white px-6 py-12 text-center">
      <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-[var(--slaw-primary-soft)]">
        <svg className="h-8 w-8 text-[var(--slaw-primary-strong)]" viewBox="0 0 32 32" fill="none" aria-hidden>
          <path d="M8 6h12l4 4v16H8V6z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
          <path d="M20 6v4h4" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
          <path d="M12 16h8M12 20h8M12 24h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </div>
      <h2 className="text-lg font-semibold text-[var(--slaw-ink)]">
        No benefits met the confidence threshold
      </h2>
      <p className="mx-auto mt-2 max-w-sm text-sm text-[var(--slaw-ink-soft)]">
        Your profile didn&rsquo;t trigger any high-confidence entitlements.
        Try adjusting your details — household status, canton, or income —
        and run the scan again.
      </p>
      <button
        type="button"
        onClick={onReset}
        className="mt-5 inline-flex items-center gap-1.5 rounded-md bg-[var(--slaw-primary)] px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[var(--slaw-primary-strong)]"
      >
        Adjust profile
      </button>
    </div>
  );
}

export default function ResultsPage() {
  const router = useRouter();
  const [report, setReport] = useState<BenefitReport | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const raw = sessionStorage.getItem("benefit_report");
    if (!raw) {
      router.replace("/");
      return;
    }
    setReport(JSON.parse(raw) as BenefitReport);
    setHydrated(true);
  }, [router]);

  const summary = useMemo(() => {
    if (!report) return { count: 0, valueMin: 0, valueMax: 0, hasValue: false };
    let valueMin = 0;
    let valueMax = 0;
    let hasValue = false;
    for (const b of report.benefits) {
      const v = b.estimated_value_chf;
      if (v && ((v.min ?? 0) || (v.max ?? 0))) {
        valueMin += v.min ?? 0;
        valueMax += v.max ?? 0;
        hasValue = true;
      }
    }
    return { count: report.benefits.length, valueMin, valueMax, hasValue };
  }, [report]);

  const generated = report
    ? new Date(report.generated_at).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "";

  if (!hydrated) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <div className="mb-8 space-y-3">
          <div className="slaw-skeleton h-8 w-2/3" />
          <div className="slaw-skeleton h-4 w-1/2" />
        </div>
        <div className="space-y-5">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </main>
    );
  }
  if (!report) return null;

  return (
    <div className="min-h-[100dvh] pb-32">
      <main className="mx-auto max-w-3xl px-4 pt-8 pb-10 sm:px-6 sm:pt-12">
        {/* Hero */}
        <header className="mb-8">
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--slaw-primary-strong)]">
            Rights Scan
          </span>
          <h1 className="mt-1 text-3xl font-bold tracking-tight text-[var(--slaw-ink)] sm:text-4xl">
            Your personalized report
          </h1>
          <p className="mt-2 max-w-xl text-sm text-[var(--slaw-ink-soft)]">
            Based on the profile you submitted, here are the Swiss legal
            entitlements, deductions, and protections we identified — each
            grounded in cited federal or cantonal law.
          </p>
        </header>

        {/* Summary strip */}
        <section className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-[var(--slaw-line)] bg-white px-4 py-3 shadow-sm">
            <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--slaw-ink-muted)]">
              Benefits found
            </div>
            <div className="mt-1 text-2xl font-bold text-[var(--slaw-ink)]">
              {summary.count}
            </div>
          </div>
          <div className="rounded-lg border border-[var(--slaw-line)] bg-white px-4 py-3 shadow-sm">
            <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--slaw-ink-muted)]">
              Total estimated value
            </div>
            <div className="mt-1 text-2xl font-bold text-[var(--slaw-ink)]">
              {summary.hasValue ? (
                <>
                  CHF {summary.valueMin.toLocaleString()}
                  <span className="mx-1 text-[var(--slaw-ink-muted)]">–</span>
                  {summary.valueMax.toLocaleString()}
                </>
              ) : (
                <span className="text-base font-medium text-[var(--slaw-ink-muted)]">
                  Not quantified
                </span>
              )}
            </div>
          </div>
          <div className="rounded-lg border border-[var(--slaw-line)] bg-white px-4 py-3 shadow-sm">
            <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--slaw-ink-muted)]">
              Suppressed
            </div>
            <div className="mt-1 text-2xl font-bold text-[var(--slaw-ink)]">
              {report.suppressed_count}
            </div>
            <div className="text-[11px] text-[var(--slaw-ink-muted)]">
              low confidence
            </div>
          </div>
          <div className="rounded-lg border border-[var(--slaw-line)] bg-white px-4 py-3 shadow-sm">
            <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--slaw-ink-muted)]">
              Generated
            </div>
            <div className="mt-1 text-sm font-semibold leading-snug text-[var(--slaw-ink)]">
              {generated}
            </div>
          </div>
        </section>

        {/* Benefits list */}
        {report.benefits.length === 0 ? (
          <EmptyState onReset={() => router.push("/")} />
        ) : (
          <div className="space-y-5">
            {report.benefits.map((b) => (
              <BenefitCard key={b.entitlement_id} benefit={b} />
            ))}
          </div>
        )}

        <p className="mx-auto mt-10 max-w-md text-center text-xs text-[var(--slaw-ink-muted)]">
          This report is informational. It is not a substitute for advice
          from a Swiss attorney registered with a cantonal bar.
        </p>
      </main>

      {/* Sticky bottom action bar */}
      <div className="slaw-no-print fixed inset-x-0 bottom-0 z-30 border-t border-[var(--slaw-line)] bg-white/85 px-4 py-3 backdrop-blur sm:px-6">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => router.push("/")}
            className="inline-flex items-center gap-1.5 rounded-md border border-[var(--slaw-line-strong)] bg-white px-4 py-2 text-sm font-semibold text-[var(--slaw-ink)] shadow-sm transition-colors hover:bg-[var(--slaw-bg-elev)]"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 14 14" fill="none" aria-hidden>
              <path d="M9 3L5 7l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Run another scan
          </button>
          <button
            type="button"
            onClick={() => window.print()}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--slaw-primary)] px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[var(--slaw-primary-strong)]"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 14 14" fill="none" aria-hidden>
              <path d="M4 2h6v3H4V2zM3 5h8v4H3V5zM4 9h6v3H4V9z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round" />
            </svg>
            Download as PDF
          </button>
        </div>
      </div>
    </div>
  );
}
