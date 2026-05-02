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
