"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BenefitCard } from "@/components/BenefitCard";
import type { BenefitReport } from "@/lib/api-client";

export default function ResultsPage() {
  const router = useRouter();
  const [report, setReport] = useState<BenefitReport | null>(null);

  useEffect(() => {
    const raw = sessionStorage.getItem("benefit_report");
    if (!raw) {
      router.replace("/");
      return;
    }
    setReport(JSON.parse(raw) as BenefitReport);
  }, [router]);

  if (!report) {
    return (
      <main className="mx-auto max-w-3xl p-8">
        <p className="text-gray-500">Loading results…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl p-8">
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-emerald-800">Your Rights Scan Results</h1>
        <p className="mt-1 text-sm text-gray-500">
          Generated at {new Date(report.generated_at).toLocaleString()} &middot;{" "}
          {report.benefits.length} benefits found &middot;{" "}
          {report.suppressed_count} suppressed (low confidence)
        </p>
      </header>

      {report.benefits.length === 0 ? (
        <p className="rounded border bg-white p-6 text-gray-600">
          No benefits met the confidence threshold for your profile. Try adjusting your profile details.
        </p>
      ) : (
        <div className="space-y-4">
          {report.benefits.map((b) => (
            <BenefitCard key={b.entitlement_id} benefit={b} />
          ))}
        </div>
      )}

      <div className="mt-8">
        <button
          onClick={() => router.push("/")}
          className="rounded border border-emerald-700 px-4 py-2 text-sm text-emerald-700 hover:bg-emerald-50"
        >
          &larr; Run another scan
        </button>
      </div>

      <p className="mt-6 text-center text-xs text-gray-400">
        Not a substitute for advice from a Swiss attorney registered with a cantonal bar.
      </p>
    </main>
  );
}
