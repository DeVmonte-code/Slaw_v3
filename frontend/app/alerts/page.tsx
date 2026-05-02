"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { api, getOrCreateUserId, type Alert } from "@/lib/api-client";

const KIND_STYLES: Record<Alert["kind"], { label: string; className: string }> = {
  NEW: {
    label: "New",
    className: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200",
  },
  UPDATED: {
    label: "Updated",
    className: "bg-amber-100 text-amber-800 ring-1 ring-amber-200",
  },
  GONE: {
    label: "Gone",
    className: "bg-slate-100 text-slate-700 ring-1 ring-slate-200",
  },
};

function formatRange(min: number, max: number): string {
  const fmt = new Intl.NumberFormat("de-CH", { maximumFractionDigits: 0 });
  return `${fmt.format(min)}-${fmt.format(max)} CHF`;
}

export default function AlertsPage() {
  const [userId, setUserId] = useState<string>("");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);

  const refresh = useCallback(
    async (uid: string, only: boolean) => {
      setLoading(true);
      const { data, error } = await api.GET("/users/{user_id}/alerts", {
        params: { path: { user_id: uid }, query: { unread_only: only } },
      });
      setLoading(false);
      if (error || !data) {
        // 404 just means "no profile saved yet" — not an error worth shouting about.
        const status = (error as { status?: number } | undefined)?.status;
        if (status === 404) {
          setAlerts([]);
          setError(null);
          return;
        }
        setError(String(error ?? "Failed to load alerts"));
        return;
      }
      setAlerts(data.alerts);
      setError(null);
    },
    [],
  );

  useEffect(() => {
    const uid = getOrCreateUserId();
    setUserId(uid);
    if (uid) void refresh(uid, unreadOnly);
  }, [refresh, unreadOnly]);

  const markRead = async (alertId: string) => {
    if (!userId) return;
    // Optimistic update so the UI is responsive even on slow networks.
    setAlerts((prev) =>
      prev.map((a) =>
        a.alert_id === alertId
          ? { ...a, read_at: new Date().toISOString() }
          : a,
      ),
    );
    await api.POST("/users/{user_id}/alerts/{alert_id}/read", {
      params: { path: { user_id: userId, alert_id: alertId } },
    });
  };

  return (
    <main className="mx-auto max-w-3xl p-8">
      <header className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-emerald-800">Your Alerts</h1>
          <p className="mt-1 text-sm text-gray-500">
            Updates from the nightly Rights Sweep — new entitlements, removed
            ones, and changes to value or cited articles.
          </p>
        </div>
        <Link
          href="/"
          className="rounded border border-emerald-700 px-3 py-1.5 text-xs text-emerald-700 hover:bg-emerald-50"
        >
          Edit profile
        </Link>
      </header>

      <div className="mb-4 flex items-center gap-3 text-sm">
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            checked={unreadOnly}
            onChange={(e) => setUnreadOnly(e.target.checked)}
          />
          Unread only
        </label>
        <span className="text-gray-400">·</span>
        <button
          onClick={() => userId && refresh(userId, unreadOnly)}
          className="text-emerald-700 hover:underline"
        >
          Refresh
        </button>
      </div>

      {loading && <p className="text-gray-500">Loading…</p>}
      {error && <p className="text-red-600">{error}</p>}

      {!loading && !error && alerts.length === 0 && (
        <div className="rounded border bg-white p-6 text-gray-600">
          <p className="font-medium">No alerts yet.</p>
          <p className="mt-1 text-sm">
            The nightly sweep runs once you opt in from the wizard. After the
            first night, this inbox shows what changed since your last scan.
          </p>
        </div>
      )}

      <ul className="space-y-3">
        {alerts.map((a) => {
          const style = KIND_STYLES[a.kind];
          const unread = !a.read_at;
          return (
            <li
              key={a.alert_id}
              className={`rounded border bg-white p-4 ${
                unread ? "border-emerald-300" : "border-gray-200 opacity-80"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${style.className}`}
                  >
                    {style.label}
                  </span>
                  <h2 className="text-base font-semibold text-gray-900">
                    {a.payload.title}
                  </h2>
                </div>
                {unread && (
                  <button
                    onClick={() => markRead(a.alert_id)}
                    className="text-xs text-emerald-700 hover:underline"
                  >
                    Mark read
                  </button>
                )}
              </div>

              <p className="mt-2 text-sm text-gray-700">
                Estimated value:{" "}
                <span className="font-medium">
                  {formatRange(
                    a.payload.estimated_value_chf_min,
                    a.payload.estimated_value_chf_max,
                  )}
                </span>
                {a.payload.previous_estimated_value_chf_min != null &&
                  a.payload.previous_estimated_value_chf_max != null && (
                    <span className="text-gray-500">
                      {" "}
                      (was{" "}
                      {formatRange(
                        a.payload.previous_estimated_value_chf_min,
                        a.payload.previous_estimated_value_chf_max,
                      )}
                      )
                    </span>
                  )}
              </p>

              {(a.payload.changed_citations ?? []).length > 0 && (
                <p className="mt-1 text-xs text-amber-800">
                  Triggered by Fedlex amendment
                  {a.payload.fedlex_amendment_date
                    ? ` (effective ${a.payload.fedlex_amendment_date})`
                    : ""}
                  : {(a.payload.changed_citations ?? []).join(", ")}
                </p>
              )}

              <p className="mt-2 text-[11px] text-gray-400">
                {new Date(a.created_at).toLocaleString()} ·{" "}
                {a.payload.category} · {a.payload.entitlement_id}
              </p>
            </li>
          );
        })}
      </ul>
    </main>
  );
}
