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
        onClick={() => setOpen(true)}
        className="mt-3 text-sm text-emerald-700 underline"
      >
        Ask a follow-up question
      </button>
    );
  }

  return (
    <div className="mt-3 rounded border bg-gray-50 p-3">
      <textarea
        value={q}
        onChange={(e) => setQ(e.target.value)}
        rows={3}
        placeholder="Ask about this specific entitlement…"
        className="w-full rounded border px-2 py-1 text-sm"
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          onClick={ask}
          disabled={loading || !q}
          className="rounded bg-emerald-600 px-3 py-1 text-sm text-white disabled:opacity-50"
        >
          {loading ? "Thinking…" : "Ask"}
        </button>
        <button onClick={() => setOpen(false)} className="text-sm text-gray-600">
          close
        </button>
      </div>
      {a && <pre className="mt-3 whitespace-pre-wrap text-sm">{a}</pre>}
    </div>
  );
}
