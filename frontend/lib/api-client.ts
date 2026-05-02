import createClient from "openapi-fetch";
import type { paths } from "./api-types";

const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = createClient<paths>({ baseUrl });

export type ContextProfile =
  paths["/scan"]["post"]["requestBody"]["content"]["application/json"];
export type BenefitReport =
  paths["/scan"]["post"]["responses"]["200"]["content"]["application/json"];
export type Benefit = BenefitReport["benefits"][number];
export type Citation = Benefit["citations"][number];

// ----- Stateful sweep types (Task #22) -------------------------------------
export type UserRecord =
  paths["/users/{user_id}/profile"]["post"]["responses"]["200"]["content"]["application/json"];
export type AlertList =
  paths["/users/{user_id}/alerts"]["get"]["responses"]["200"]["content"]["application/json"];
export type Alert = AlertList["alerts"][number];

const USER_ID_KEY = "slaw_user_id";

/** Get-or-create the per-browser user_id stored in localStorage.
 *
 * Server-side rendering safety: returns "" when ``window`` is undefined
 * so the wizard can opt-out of the sweep cleanly when the toggle is off.
 * Callers must guard against the empty string before POSTing. */
export function getOrCreateUserId(): string {
  if (typeof window === "undefined") return "";
  let id = window.localStorage.getItem(USER_ID_KEY);
  if (!id) {
    id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `u-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem(USER_ID_KEY, id);
  }
  return id;
}
