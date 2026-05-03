"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { BenefitCard } from "@/components/BenefitCard";
import {
  api,
  getOrCreateUserId,
  type BenefitReport,
  type ContextProfile,
} from "@/lib/api-client";

const PHASES = [
  "Reading your profile",
  "Searching Swiss federal law",
  "Cross-checking cantonal rules",
  "Drafting your report",
];
/** Approximate scan budget (s) used to drive the indeterminate bar.
 *  Caps at 95% so we never falsely "complete" before the response. */
const EXPECTED_SECS = 35;

function fmtElapsed(s: number) {
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

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

function ScanInProgress({ elapsed }: { elapsed: number }) {
  const phaseIdx = Math.min(PHASES.length - 1, Math.floor(elapsed / 5));
  // Logarithmic-ish curve that grows fast early, slows, and caps at 95%
  // of EXPECTED_SECS. Even past expected, we pin to 95.
  const ratio = Math.min(1, elapsed / EXPECTED_SECS);
  const pct = Math.min(95, Math.round(8 + 87 * (1 - Math.pow(1 - ratio, 2))));

  return (
    <div className="mb-8">
      <div className="rounded-xl border border-[var(--slaw-line)] bg-white p-6 shadow-sm sm:p-7">
        <div className="flex items-center gap-3">
          <svg
            className="h-5 w-5 animate-spin text-[var(--slaw-primary)]"
            viewBox="0 0 20 20"
            fill="none"
            aria-hidden
          >
            <circle cx="10" cy="10" r="7" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.5" />
            <path d="M17 10a7 7 0 0 0-7-7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
          </svg>
          <h2 className="text-lg font-semibold text-[var(--slaw-ink)]">
            Scanning your rights…
          </h2>
        </div>

        <p
          key={phaseIdx}
          className="mt-3 text-sm text-[var(--slaw-ink-soft)] transition-opacity duration-500"
          aria-live="polite"
        >
          {PHASES[phaseIdx]}
          {phaseIdx < PHASES.length - 1 ? "…" : "…"}
        </p>

        <div
          className="mt-4 h-2 overflow-hidden rounded-full bg-[var(--slaw-line)]"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          aria-label="Scan progress"
        >
          <div
            className="h-full rounded-full bg-[var(--slaw-primary)] transition-[width] duration-700 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>

        <div className="mt-2 flex items-center justify-between text-xs text-[var(--slaw-ink-muted)]">
          <span>{fmtElapsed(elapsed)} elapsed · usually 20–60 s</span>
          <span>
            Step {phaseIdx + 1} of {PHASES.length}
          </span>
        </div>

        <p className="mt-4 rounded-md bg-[var(--slaw-bg-elev)] px-3 py-2 text-xs text-[var(--slaw-ink-muted)]">
          Keep this tab open — your report will appear here as soon as
          it&rsquo;s ready. We&rsquo;re reading federal and cantonal sources
          and grounding every result in a citation.
        </p>
      </div>

      <div className="mt-5 space-y-5" aria-hidden>
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    </div>
  );
}

function ScanError({
  message,
  onRetry,
  onEdit,
}: {
  message: string;
  onRetry: () => void;
  onEdit: () => void;
}) {
  return (
    <div
      role="alert"
      className="mb-8 rounded-xl border border-red-200 bg-[var(--slaw-danger-bg)] p-6 shadow-sm sm:p-7"
    >
      <div className="flex items-start gap-3">
        <svg className="mt-0.5 h-5 w-5 shrink-0 text-[var(--slaw-danger)]" viewBox="0 0 20 20" fill="none" aria-hidden>
          <circle cx="10" cy="10" r="8.5" stroke="currentColor" strokeWidth="1.5" />
          <path d="M10 5.5v5M10 13.5v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-[var(--slaw-danger)]">
            We couldn&rsquo;t finish your scan
          </h2>
          <p className="mt-1 break-words text-sm text-[var(--slaw-danger)]/90">
            {message}
          </p>
          <p className="mt-2 text-xs text-[var(--slaw-ink-soft)]">
            Your profile is still saved — you can try again or edit a few
            answers.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-1.5 rounded-md bg-[var(--slaw-primary)] px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[var(--slaw-primary-strong)]"
            >
              Try again
            </button>
            <button
              type="button"
              onClick={onEdit}
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--slaw-line-strong)] bg-white px-4 py-2 text-sm font-semibold text-[var(--slaw-ink)] shadow-sm transition-colors hover:bg-[var(--slaw-bg-elev)]"
            >
              Edit profile
            </button>
          </div>
        </div>
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

type Status = "loading" | "pending" | "ready" | "error";

export default function ResultsPage() {
  const router = useRouter();
  const [status, setStatus] = useState<Status>("loading");
  const [report, setReport] = useState<BenefitReport | null>(null);
  const [error, setError] = useState<string>("");
  const [elapsed, setElapsed] = useState(0);
  const [scanNonce, setScanNonce] = useState(0);
  // Guard so React 18 strict-mode double-mount doesn't fire two /scan
  // requests in dev.
  const inFlight = useRef(false);

  // Hydrate: do we have a finished report? a pending request? or nothing?
  useEffect(() => {
    const cached = sessionStorage.getItem("benefit_report");
    if (cached) {
      try {
        setReport(JSON.parse(cached) as BenefitReport);
        setStatus("ready");
        return;
      } catch {
        sessionStorage.removeItem("benefit_report");
      }
    }
    const pending = sessionStorage.getItem("benefit_report_pending");
    const profileRaw = sessionStorage.getItem("scan_profile");
    if (pending && profileRaw) {
      setStatus("pending");
      return;
    }
    router.replace("/");
  }, [router]);

  // Drive the actual /scan request whenever we enter the pending state
  // (initial load or a "Try again" click bumps `scanNonce`).
  useEffect(() => {
    if (status !== "pending") return;
    if (inFlight.current) return;
    const profileRaw = sessionStorage.getItem("scan_profile");
    if (!profileRaw) {
      router.replace("/");
      return;
    }
    let cleaned: ContextProfile;
    try {
      cleaned = JSON.parse(profileRaw) as ContextProfile;
    } catch {
      sessionStorage.removeItem("scan_profile");
      sessionStorage.removeItem("benefit_report_pending");
      router.replace("/");
      return;
    }
    inFlight.current = true;
    setElapsed(0);
    const started = Date.now();
    const tick = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000));
    }, 1000);

    (async () => {
      const { data, error: apiErr } = await api.POST("/scan", { body: cleaned });
      window.clearInterval(tick);
      inFlight.current = false;
      if (apiErr || !data) {
        setError(
          String(apiErr ?? "Unknown error — is the backend running?"),
        );
        setStatus("error");
        return;
      }
      try {
        sessionStorage.setItem("benefit_report", JSON.stringify(data));
        sessionStorage.removeItem("benefit_report_pending");
      } catch {
        /* non-fatal */
      }
      setReport(data);
      setStatus("ready");

      // Fire-and-forget sweep upsert (matches old wizard behavior).
      const notifyEnabled =
        sessionStorage.getItem("scan_notify_enabled") !== "0";
      const userId = getOrCreateUserId();
      if (userId) {
        api
          .POST("/users/{user_id}/profile", {
            params: { path: { user_id: userId } },
            body: { profile: cleaned, notify_enabled: notifyEnabled },
          })
          .catch((e) => {
            // eslint-disable-next-line no-console
            console.warn("sweep_profile_upsert_failed", e);
          });
      }
    })();

    return () => {
      window.clearInterval(tick);
    };
  }, [status, scanNonce, router]);

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

  // Initial hydration flicker — keep it short and content-shaped.
  if (status === "loading") {
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

  return (
    <div className="min-h-[100dvh] pb-32">
      <main className="mx-auto max-w-3xl px-4 pt-8 pb-10 sm:px-6 sm:pt-12">
        {/* Hero */}
        <header className="mb-8">
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--slaw-primary-strong)]">
            Rights Scan
          </span>
          <h1 className="mt-1 text-3xl font-bold tracking-tight text-[var(--slaw-ink)] sm:text-4xl">
            {status === "ready" ? "Your personalized report" : "Your scan is running"}
          </h1>
          <p className="mt-2 max-w-xl text-sm text-[var(--slaw-ink-soft)]">
            {status === "ready"
              ? "Based on the profile you submitted, here are the Swiss legal entitlements, deductions, and protections we identified — each grounded in cited federal or cantonal law."
              : "We're matching your profile against Swiss federal and cantonal sources. This typically takes 20 to 60 seconds."}
          </p>
        </header>

        {status === "pending" && <ScanInProgress elapsed={elapsed} />}

        {status === "error" && (
          <ScanError
            message={error}
            onRetry={() => {
              setError("");
              setStatus("pending");
              setScanNonce((n) => n + 1);
            }}
            onEdit={() => router.push("/")}
          />
        )}

        {status === "ready" && report && (
          <>
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
          </>
        )}
      </main>

      {/* Sticky bottom action bar — only meaningful once results are in */}
      {status === "ready" && (
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
      )}
    </div>
  );
}
