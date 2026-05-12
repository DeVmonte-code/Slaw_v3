Read [](file:///Users/luiscastillo/Desktop/Luis_Environment_Structure/Processes/Support_Processes/Research%20and%20Development%20%28R%26D%29/Slaw/Slaw_V3/Slaw_v3/prompt/Slaw_V3.md#1638-1638), lines 1638 to 1680

The file continues — there's a full **Prompt B** for the frontend. Let me read it all. 

Read [](file:///Users/luiscastillo/Desktop/Luis_Environment_Structure/Processes/Support_Processes/Research%20and%20Development%20%28R%26D%29/Slaw/Slaw_V3/Slaw_v3/prompt/Slaw_V3.md#1680-1680), lines 1680 to 1900

Read [](file:///Users/luiscastillo/Desktop/Luis_Environment_Structure/Processes/Support_Processes/Research%20and%20Development%20%28R%26D%29/Slaw/Slaw_V3/Slaw_v3/prompt/Slaw_V3.md#1900-1900), lines 1900 to 2150

Read [](file:///Users/luiscastillo/Desktop/Luis_Environment_Structure/Processes/Support_Processes/Research%20and%20Development%20%28R%26D%29/Slaw/Slaw_V3/Slaw_v3/prompt/Slaw_V3.md#2150-2150), lines 2150 to 2390

Read [](file:///Users/luiscastillo/Desktop/Luis_Environment_Structure/Processes/Support_Processes/Research%20and%20Development%20%28R%26D%29/Slaw/Slaw_V3/Slaw_v3)

Analyzing your answers...

Created memory file [](file:///Users/luiscastillo/Library/Application%20Support/Code/User/workspaceStorage/16efa7d1005dd2b6f9e5e4c87efe2a7f/GitHub.copilot-chat/memory-tool/memories/MjIyZmI4YTQtYmZiNC00YThkLTgxMmMtZTE0OWUwNTliZTEw/plan.md)

Updated memory file [](file:///Users/luiscastillo/Library/Application%20Support/Code/User/workspaceStorage/16efa7d1005dd2b6f9e5e4c87efe2a7f/GitHub.copilot-chat/memory-tool/memories/MjIyZmI4YTQtYmZiNC00YThkLTgxMmMtZTE0OWUwNTliZTEw/plan.md)

Deleted memory [](file:///Users/luiscastillo/Library/Application%20Support/Code/User/workspaceStorage/16efa7d1005dd2b6f9e5e4c87efe2a7f/GitHub.copilot-chat/memory-tool/memories/MjIyZmI4YTQtYmZiNC00YThkLTgxMmMtZTE0OWUwNTliZTEw/plan.md)

Created memory file [](file:///Users/luiscastillo/Library/Application%20Support/Code/User/workspaceStorage/16efa7d1005dd2b6f9e5e4c87efe2a7f/GitHub.copilot-chat/memory-tool/memories/MjIyZmI4YTQtYmZiNC00YThkLTgxMmMtZTE0OWUwNTliZTEw/plan.md)

The backend sprint is done — Prompt A ends here. Prompt B is the frontend. Here's the plan:

---

## Plan: Slaw Frontend Sprint (Prompt B) — Next.js 15

**TL;DR:** Build `swiss-legal-web` — a Next.js 15 App Router app with Tailwind, TypeScript types auto-generated from the backend's openapi.json. Three screens: profile wizard → results page with benefit cards → per-card follow-up chat drawer. 7 phases, each `STOP`-gated.

**Location:** `Slaw_V3/swiss-legal-web/` (sibling to `Slaw_v3/`)

**Steps**

1. **F0 — Bootstrap** — Create `swiss-legal-web/`, write all 11 root/app files (exact spec content), `pnpm install && pnpm build`, verify `curl localhost:3000` renders placeholder
2. **F1 — Generate API Types** *(depends on F0 + backend running)* — `pnpm run types:api` hits `localhost:8000/openapi.json`, writes `lib/api-types.ts`; verify >100 lines, `ContextProfile` + `BenefitReport` present
3. **F2 — API Client** *(depends on F1)* — Create `lib/api-client.ts` with `openapi-fetch`; export `ContextProfile`, `BenefitReport`, `Benefit`, `Citation` convenience types
4. **F3 — Profile Wizard** *(depends on F2)* — Replace `app/page.tsx` with full client form; submits → `POST /scan` → `sessionStorage` → redirect `/results`; all fields default to Luis-profile values
5. **F4 — Results Page** *(depends on F3)* — Create `app/results/page.tsx` + `components/BenefitCard.tsx`; reads `sessionStorage`, renders ranked cards with citations, confidence %, evidence, reasoning, disclaimer
6. **F5 — Follow-up Chat** *(depends on F4)* — Create `components/AskFollowUp.tsx`; add to `BenefitCard`; toggle drawer → textarea → `POST /chat` → rendered answer
7. **F6 — Docker Prep** *(depends on F5)* — `Dockerfile` (3-stage node:20-alpine) + `.dockerignore`; build is optional/informational
8. **F7 — E2E Smoke** *(depends on F6)* — smoke.sh: backend reachable → `types:api` → build → start → curl HTML assertions → `=== Frontend smoke PASSED ===`

**Relevant files**
- `lib/api-types.ts` — generated, never hand-edited
- `lib/api-client.ts` — typed `openapi-fetch` client
- `app/page.tsx` — profile wizard
- `app/results/page.tsx` — results list
- `components/BenefitCard.tsx` + `components/AskFollowUp.tsx`
- `Dockerfile`, `.dockerignore`, smoke.sh

**Verification**
1. `pnpm build` exits 0 after every phase
2. F7 smoke exits 0 and ends with `=== Frontend smoke PASSED ===`
3. Manual: fill form → submit → ≥5 benefit cards with citations, confidence, evidence, chat drawer

**Decisions**
- Sibling directory `Slaw_V3/swiss-legal-web/` — no mixing with the backend repo
- Tailwind only; no UI library
- No auth, streaming, i18n, PDF in this sprint
- `sessionStorage` is the bridge between `/` and `/results`

**Further Considerations**
1. `BenefitReport.suppressed_count` — the results page references this field; will verify it exists in openapi.json before F4 and adjust if absent
2. F1 (`types:api`) and F7 (smoke) both require the backend running — start with `set -a && source .env && set +a && uvicorn swiss_legal_api.api.main:app --port 8000` before those phases

---

Ready to start? Type `continue` to begin F0.