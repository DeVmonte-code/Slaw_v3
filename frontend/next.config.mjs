/** @type {import('next').NextConfig} */
const BACKEND_INTERNAL_URL =
  process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

const PROXIED_PATHS = [
  "/scan",
  "/scan/stream",
  "/chat",
  "/audits",
  "/audits/:path*",
  "/admin/:path*",
  "/users/:path*",
  "/health",
  "/healthz",
  "/readyz",
  "/openapi.json",
];

export default {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "",
  },
  async rewrites() {
    return PROXIED_PATHS.map((source) => ({
      source,
      destination: `${BACKEND_INTERNAL_URL}${source}`,
    }));
  },
};
