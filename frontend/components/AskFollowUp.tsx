"use client";
import { useState } from "react";
import { api } from "@/lib/api-client";

export function AskFollowUp({ benefitId }: { benefitId: string }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [a, setA] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function ask() {
    setLoading(true);
    setA(null);
    const { data, error } = await api.POST("/chat", {
      body: { message: q, benefit_id: benefitId },
    });
    setLoading(false);
    setA(error ? String(error) : (data?.answer ?? ""));
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-1.5 text-sm font-medium text-[var(--slaw-primary-strong)] shadow-sm transition-colors hover:border-[var(--slaw-primary)] hover:bg-[var(--slaw-primary-soft)]"
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 14 14" fill="none" aria-hidden>
          <path d="M2 3h10v6H6l-3 3V9H2V3z" stroke="currentColor" strokeWidth="1.25" strokeLinejoin="round" />
        </svg>
        Ask a follow-up question
      </button>
    );
  }

  return (
    <div className="rounded-lg border border-[var(--slaw-line-strong)] bg-[var(--slaw-bg-elev)] p-3 shadow-sm">
      <label className="block text-[11px] font-medium uppercase tracking-wider text-[var(--slaw-ink-muted)]">
        Your question about this entitlement
      </label>
      <textarea
        value={q}
        onChange={(e) => setQ(e.target.value)}
        rows={3}
        placeholder="e.g. Does this still apply if my lease is shared?"
        className="mt-1 w-full resize-y rounded-md border border-[var(--slaw-line-strong)] bg-white px-3 py-2 text-sm text-[var(--slaw-ink)] shadow-sm focus:border-[var(--slaw-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--slaw-primary)]"
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={ask}
          disabled={loading || !q}
          className="inline-flex items-center gap-1.5 rounded-md bg-[var(--slaw-primary)] px-3 py-1.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-[var(--slaw-primary-strong)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading && (
            <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 14 14" fill="none" aria-hidden>
              <circle cx="7" cy="7" r="5" stroke="currentColor" strokeOpacity="0.3" strokeWidth="2" />
              <path d="M12 7a5 5 0 0 0-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          )}
          {loading ? "Thinking…" : "Ask"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-sm text-[var(--slaw-ink-muted)] hover:text-[var(--slaw-ink)]"
        >
          Close
        </button>
      </div>
      {a && (
        <div className="mt-3 rounded-md border border-[var(--slaw-line)] bg-white p-3">
          <p className="text-[11px] font-medium uppercase tracking-wider text-[var(--slaw-ink-muted)]">
            Answer
          </p>
          <pre className="mt-1 whitespace-pre-wrap font-sans text-sm leading-relaxed text-[var(--slaw-ink)]">
            {a}
          </pre>
        </div>
      )}
    </div>
  );
}
