# Slaw v3 — Phase 2 Sprint: ContextProfile Enrichment (26 Missing Fields)
## Replit Agent Prompt

> **Context:** Phase 1 (Task #63) completed successfully.
> `backend/diagnostics/profile_audit.json` is the authoritative source of truth.
> It confirms: 26 fields present, 26 fields missing, smoke_test_result=pass, benefit_count=12.
> This prompt is Phase 2 — adding all 26 missing fields to the model, types, constants, and wizard UI.
>
> **Execution order:** 2A and 2B run in parallel (different files). 2C requires 2A. 2D requires 2B + 2C.
> 2E (validation gate) requires 2A + 2B + 2C + 2D all complete. Do not skip or reorder.

---

## PHASE 2A — BACKEND PYDANTIC MODEL
### ⛔ BLOCKING for Phase 2C

### What & Why
Phase 1 confirmed that 26 fields required to gate Swiss-law entitlements are absent from
`ContextProfile`. This phase adds all 26 to the Pydantic v2 model with safe `Optional` / default
values so no existing fixture breaks. The exact fields come directly from
`backend/diagnostics/profile_audit.json` `missing_fields` array — do not invent or omit any.

### Done looks like
- All 26 fields are present as attributes on `ContextProfile` with the exact types and defaults
  specified below.
- `ContextProfile()` (zero-arg instantiation) succeeds without error.
- `ContextProfile(**luis_fixture)` where `luis_fixture` is the contents of
  `backend/fixtures/luis_profile.json` continues to succeed (backward compatibility).
- Re-running the Phase 1 audit script produces `missing_fields: []`.
- `python -m pytest backend/ -x -q` exits 0 with no new failures.

### Out of scope
- Do NOT add new entitlement seed entries.
- Do NOT modify the trigger evaluator logic.
- Do NOT touch any frontend file.
- Do NOT rename or remove any of the 26 existing fields already on the model.
- Do NOT add new test files — only update the model.
- Do NOT add `children_ages` — it is not in the 26 missing fields from the audit.

### Done looks like (technical guardrails)
```bash
# Gate command — must exit 0 before declaring Phase 2A complete
python - <<'EOF'
from backend.src.swiss_legal_api.schemas.context_profile import ContextProfile
import json

# Zero-arg instantiation
p = ContextProfile()

# All 26 fields must exist
MISSING_26 = [
    "ahv_contribution_gap_years", "alimony_paid_chf_yearly",
    "alv_contribution_months_last_2y", "bvg_plan_type",
    "charitable_donations_chf_yearly", "disability_iv_grade",
    "employment_contract_type", "gross_income_chf_yearly",
    "has_property_damage_dispute", "has_received_termination_notice",
    "health_insurance_franchise_chf", "home_office_days_weekly",
    "is_caring_for_dependent_adult", "is_cross_border_commuter",
    "is_on_sick_leave", "is_quellensteuer_subject",
    "is_survivor_with_dependents", "kurzarbeit_or_partial_unemployment",
    "last_rent_increase_year", "lease_type",
    "maternity_expected_date", "paternity_leave_taken",
    "personal_note", "professional_association_fees_chf",
    "received_tenancy_termination", "tenancy_deposit_chf",
]
for f in MISSING_26:
    assert hasattr(p, f), f"MISSING: {f}"

# Backward compat: luis fixture must still load
with open("backend/fixtures/luis_profile.json") as fh:
    fixture = json.load(fh)
p2 = ContextProfile(**fixture)
print(f"OK — all 26 fields present, luis fixture loads. benefit_count field present: {hasattr(p2, 'benefit_count') or True}")
print("PHASE 2A GATE: PASSED")
EOF
```

### Steps

1. Open `backend/src/swiss_legal_api/schemas/context_profile.py`.

2. Add the following imports at the top if not already present:
```python
from typing import Optional, Literal
from pydantic import Field
```

3. Append the following block inside the `ContextProfile` class body,
   after all existing fields, under the comment `# --- ENRICHMENT FIELDS (Phase 2) ---`:

**Group A — Employment & Location (extends Step 1):**
```python
employment_contract_type: Optional[Literal[
    "indefinite", "fixed_term", "apprenticeship"
]] = None
is_quellensteuer_subject: Optional[bool] = None
is_cross_border_commuter: bool = False
```

**Group B — Housing (extends Step 3):**
```python
lease_type: Optional[Literal[
    "indefinite", "fixed_term", "subsidized"
]] = None
last_rent_increase_year: Optional[int] = None
tenancy_deposit_chf: Optional[float] = None
```

**Group C — Income & Tax (new Step 5):**
```python
gross_income_chf_yearly: Optional[float] = None
pillar_3a_contribution_chf: Optional[float] = None
health_insurance_franchise_chf: Optional[Literal[
    300, 500, 1000, 1500, 2000, 2500
]] = None
home_office_days_weekly: Optional[int] = None
professional_association_fees_chf: Optional[float] = None
alimony_paid_chf_yearly: Optional[float] = None
charitable_donations_chf_yearly: Optional[float] = None
```

**Group D — Social Security & Disability (new Step 6):**
```python
disability_iv_grade: Optional[Literal[
    "none", "40", "50", "60", "70", "full"
]] = None
ahv_contribution_gap_years: Optional[int] = None
alv_contribution_months_last_2y: Optional[int] = None
bvg_plan_type: Optional[Literal[
    "mandatory_minimum", "extended", "executive", "none"
]] = None
```

**Group E — Event Flags (extends Step 4):**
```python
has_received_termination_notice: bool = False
is_on_sick_leave: bool = False
maternity_expected_date: Optional[str] = None   # format: "YYYY-MM"
paternity_leave_taken: bool = False
received_tenancy_termination: bool = False
has_property_damage_dispute: bool = False
is_caring_for_dependent_adult: bool = False
is_survivor_with_dependents: bool = False
kurzarbeit_or_partial_unemployment: bool = False
```

**Group F — Free Text:**
```python
personal_note: Optional[str] = Field(
    default=None,
    max_length=1000,
    description=(
        "Free-text situation description for semantic benefit signal extraction. "
        "Processed at scan time only. Not persisted to any store."
    )
)
```

4. Run the gate command above. Fix any import or syntax errors until it exits 0.

5. Run `python -m pytest backend/ -x -q` and confirm no regressions.

### Validation
```bash
python -m pytest backend/ -x -q
# Expect: all previously passing tests still pass, exit code 0
```

### Relevant files
- `backend/src/swiss_legal_api/schemas/context_profile.py` — **primary edit target**
- `backend/fixtures/luis_profile.json` — read-only reference for backward compat check
- `backend/diagnostics/profile_audit.json` — read-only reference

---

## PHASE 2B — FRONTEND CONSTANTS
### ✅ Parallel with Phase 2A (different files)

### What & Why
`SteppedWizard.tsx` must not contain hardcoded option strings. All option arrays and new
default values go into `constants.ts` so the wizard imports from a single source of truth.
This phase is independent of Phase 2A.

### Done looks like
- `frontend/components/profile-wizard/constants.ts` exports all new option arrays and an
  `ENRICHMENT_DEFAULTS` object.
- `npx tsc --noEmit` in `frontend/` exits 0.
- No option string literals for new fields appear anywhere in `SteppedWizard.tsx`.

### Out of scope
- Do NOT modify `SteppedWizard.tsx` in this phase.
- Do NOT modify `frontend/lib/api-types.ts`.
- Do NOT modify `wizard.css`.
- Do NOT modify `frontend/app/page.tsx`.

### Done looks like (technical guardrails)
```bash
cd frontend && npx tsc --noEmit && echo "PHASE 2B GATE: PASSED"
```

### Steps

1. Open `frontend/components/profile-wizard/constants.ts`.

2. Add the following exported constants at the end of the file:

```typescript
// ─── ENRICHMENT CONSTANTS (Phase 2) ──────────────────────────────────────────

export const EMPLOYMENT_CONTRACT_TYPE_OPTIONS = [
  { value: "indefinite",    label: "Open-ended (indefinite)" },
  { value: "fixed_term",    label: "Fixed-term" },
  { value: "apprenticeship", label: "Apprenticeship / traineeship" },
] as const;

export const FRANCHISE_OPTIONS = [
  { value: 300,  label: "CHF 300 — minimum" },
  { value: 500,  label: "CHF 500" },
  { value: 1000, label: "CHF 1,000" },
  { value: 1500, label: "CHF 1,500" },
  { value: 2000, label: "CHF 2,000" },
  { value: 2500, label: "CHF 2,500 — maximum" },
] as const;

export const DISABILITY_IV_GRADE_OPTIONS = [
  { value: "none", label: "No disability" },
  { value: "40",   label: "40% — quarter pension" },
  { value: "50",   label: "50% — half pension" },
  { value: "60",   label: "60% — three-quarter pension" },
  { value: "70",   label: "70%+ — full pension" },
  { value: "full", label: "Full disability" },
] as const;

export const BVG_PLAN_TYPE_OPTIONS = [
  { value: "mandatory_minimum", label: "Mandatory minimum only" },
  { value: "extended",          label: "Extended employer plan" },
  { value: "executive",         label: "Executive / Kader plan" },
  { value: "none",              label: "No pension fund (self-employed)" },
] as const;

export const LEASE_TYPE_OPTIONS = [
  { value: "indefinite", label: "Open-ended" },
  { value: "fixed_term", label: "Fixed-term" },
  { value: "subsidized", label: "Subsidized / gemeinnützig" },
] as const;

export const EVENT_CHIP_OPTIONS = [
  { value: "has_received_termination_notice",  label: "Received employment termination notice" },
  { value: "is_on_sick_leave",                 label: "Currently on sick leave" },
  { value: "paternity_leave_taken",            label: "Partner took / taking paternity leave" },
  { value: "received_tenancy_termination",     label: "Received lease termination notice" },
  { value: "has_property_damage_dispute",      label: "Dispute over deposit or property damage" },
  { value: "is_caring_for_dependent_adult",    label: "Caring for ill or disabled family member" },
  { value: "is_survivor_with_dependents",      label: "Recently widowed with dependents" },
  { value: "kurzarbeit_or_partial_unemployment", label: "On Kurzarbeit / short-time work" },
] as const;

export const ENRICHMENT_DEFAULTS = {
  // Group A — Employment
  employment_contract_type:         undefined as string | undefined,
  is_quellensteuer_subject:         undefined as boolean | undefined,
  is_cross_border_commuter:         false,
  // Group B — Housing
  lease_type:                       undefined as string | undefined,
  last_rent_increase_year:          undefined as number | undefined,
  tenancy_deposit_chf:              undefined as number | undefined,
  // Group C — Income & Tax
  gross_income_chf_yearly:          undefined as number | undefined,
  pillar_3a_contribution_chf:       undefined as number | undefined,
  health_insurance_franchise_chf:   undefined as number | undefined,
  home_office_days_weekly:          undefined as number | undefined,
  professional_association_fees_chf: undefined as number | undefined,
  alimony_paid_chf_yearly:          undefined as number | undefined,
  charitable_donations_chf_yearly:  undefined as number | undefined,
  // Group D — Social Security
  disability_iv_grade:              undefined as string | undefined,
  ahv_contribution_gap_years:       undefined as number | undefined,
  alv_contribution_months_last_2y:  undefined as number | undefined,
  bvg_plan_type:                    undefined as string | undefined,
  // Group E — Event Flags
  has_received_termination_notice:  false,
  is_on_sick_leave:                 false,
  maternity_expected_date:          undefined as string | undefined,
  paternity_leave_taken:            false,
  received_tenancy_termination:     false,
  has_property_damage_dispute:      false,
  is_caring_for_dependent_adult:    false,
  is_survivor_with_dependents:      false,
  kurzarbeit_or_partial_unemployment: false,
  // Group F — Free text
  personal_note:                    undefined as string | undefined,
};
```

3. Merge `ENRICHMENT_DEFAULTS` into the existing `DEFAULT_VALUES` export.
   Find the current `DEFAULT_VALUES` object and spread `ENRICHMENT_DEFAULTS` into it:
```typescript
export const DEFAULT_VALUES = {
  // ... all existing keys unchanged ...
  ...ENRICHMENT_DEFAULTS,
};
```

4. Run `cd frontend && npx tsc --noEmit`. Fix any type errors until it exits 0.

### Validation
```bash
cd frontend && npx tsc --noEmit
```

### Relevant files
- `frontend/components/profile-wizard/constants.ts` — **primary edit target**

---

## PHASE 2C — FRONTEND API TYPES REGENERATION
### ⚠️ Requires Phase 2A complete

### What & Why
`frontend/lib/api-types.ts` contains the TypeScript types generated from the FastAPI OpenAPI
schema. After Phase 2A adds 26 fields to the Pydantic model, the generated types must be
regenerated so the frontend TypeScript compiler enforces the updated `ContextProfile` shape.
No `any` casts are permitted as a workaround.

### Done looks like
- `frontend/lib/api-types.ts` contains all 26 new field names.
- `npx tsc --noEmit` in `frontend/` exits 0 with no type errors from new fields.
- No `any` type annotations are introduced to suppress errors.

### Out of scope
- Do NOT change FastAPI route signatures or the `/scan/stream` endpoint.
- Do NOT modify the Pydantic model further.
- Do NOT modify any component file except to fix type errors caused by the new shape.
- Do NOT change the streaming response format.

### Done looks like (technical guardrails)
```bash
# Spot-check that regenerated types contain the 7 sentinel fields
python3 - <<'EOF'
content = open("frontend/lib/api-types.ts").read()
sentinels = [
    "gross_income_chf_yearly",
    "employment_contract_type",
    "health_insurance_franchise_chf",
    "personal_note",
    "has_received_termination_notice",
    "disability_iv_grade",
    "bvg_plan_type",
]
missing = [s for s in sentinels if s not in content]
assert not missing, f"Missing from api-types.ts: {missing}"
print("All 7 sentinel fields present in api-types.ts")
EOF

cd frontend && npx tsc --noEmit && echo "PHASE 2C GATE: PASSED"
```

### Steps

1. Start the FastAPI backend on a spare port:
   ```bash
   cd backend && uvicorn src.swiss_legal_api.main:app --port 8099 &
   BGPID=$!
   sleep 4
   ```

2. Fetch the OpenAPI schema:
   ```bash
   curl -sf http://localhost:8099/openapi.json -o /tmp/slaw_openapi.json
   ```
   If this fails, check the exact uvicorn entrypoint in `backend/pyproject.toml` or
   `backend/Makefile` and use the correct module path.

3. Regenerate the TypeScript types:
   ```bash
   cd frontend
   npx openapi-typescript /tmp/slaw_openapi.json -o lib/api-types.ts
   ```

4. Kill the background server:
   ```bash
   kill $BGPID 2>/dev/null
   ```

5. Run the spot-check and TypeScript compiler:
   ```bash
   python3 - <<'EOF'
   content = open("frontend/lib/api-types.ts").read()
   sentinels = [
       "gross_income_chf_yearly", "employment_contract_type",
       "health_insurance_franchise_chf", "personal_note",
       "has_received_termination_notice", "disability_iv_grade", "bvg_plan_type",
   ]
   missing = [s for s in sentinels if s not in content]
   assert not missing, f"Missing: {missing}"
   print("Sentinel check passed")
   EOF
   cd frontend && npx tsc --noEmit
   ```

6. If `npx tsc --noEmit` reports type errors from components that now receive the new shape,
   fix them by updating the relevant prop types — do not suppress with `any`.

### Validation
```bash
cd frontend && npx tsc --noEmit
```

### Relevant files
- `frontend/lib/api-types.ts` — **regenerated by this phase, do not hand-edit**
- `backend/src/swiss_legal_api/main.py` — read-only (only needed to start the server)

---

## PHASE 2D — WIZARD UI (STEPS 1, 3, 4 EXTENSIONS + NEW STEPS 5 AND 6)
### ⚠️ Requires Phase 2B + Phase 2C complete

### What & Why
Surface all 26 new fields across the wizard. The agent's Phase 1 plan identified the correct
taxonomy: income/tax fields belong in a new Step 5, AHV/BVG/disability fields in a new Step 6.
Employment contract and cross-border flags extend Step 1. Tenancy detail fields extend Step 3.
Event chips and personal note extend Step 4. All options import from `constants.ts`.

### Done looks like
- `SteppedWizard.tsx` renders new fields in their assigned steps with conditional display logic.
- New Steps 5 and 6 are included in the wizard step array.
- The form POSTs all 26 new field keys in the request body submitted to `/scan/stream`.
- `npx tsc --noEmit` exits 0.
- `npx next build` exits 0.
- No option strings are hardcoded — all come from `constants.ts` imports.

### Out of scope
- Do NOT modify `frontend/app/page.tsx`.
- Do NOT modify any API route handler or `/scan/stream`.
- Do NOT modify scan results display components.
- Do NOT add new npm packages.
- Do NOT add Zod validation schemas for new fields in this phase.
- Do NOT add `children_ages` — it is not in the 26 missing fields.

### Done looks like (technical guardrails)
```bash
cd frontend
npx tsc --noEmit && echo "TypeScript clean"
npx next build   && echo "Build clean"
echo "PHASE 2D GATE: PASSED"
```

### Steps

Open `frontend/components/profile-wizard/SteppedWizard.tsx`.

Import the new constants at the top of the file (add to existing imports):
```tsx
import {
  EMPLOYMENT_CONTRACT_TYPE_OPTIONS,
  FRANCHISE_OPTIONS,
  DISABILITY_IV_GRADE_OPTIONS,
  BVG_PLAN_TYPE_OPTIONS,
  LEASE_TYPE_OPTIONS,
  EVENT_CHIP_OPTIONS,
  ENRICHMENT_DEFAULTS,
} from "./constants";
```

Merge `ENRICHMENT_DEFAULTS` into the initial form state:
```tsx
const [formData, setFormData] = useState({
  // ... existing initial state ...
  ...ENRICHMENT_DEFAULTS,
});
```

---

#### Step 1 extensions — after the existing `commute_km_daily` field block:

```tsx
{/* Employment contract type — shown for employed statuses */}
{(formData.employment_status === "employee_full_time" ||
  formData.employment_status === "employee_part_time") && (
  <div className="field-group">
    <label htmlFor="employment_contract_type">Employment contract type</label>
    <select
      id="employment_contract_type"
      value={formData.employment_contract_type ?? ""}
      onChange={e => setFormData(p => ({
        ...p,
        employment_contract_type: e.target.value || undefined,
      }))}
    >
      <option value="">Select…</option>
      {EMPLOYMENT_CONTRACT_TYPE_OPTIONS.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  </div>
)}

{/* Quellensteuer — shown only to non-Swiss residents without a C permit */}
{formData.nationality_status !== "swiss" && formData.permit_type !== "C" && (
  <div className="field-group checkbox-field">
    <label>
      <input
        type="checkbox"
        checked={formData.is_quellensteuer_subject ?? false}
        onChange={e => setFormData(p => ({
          ...p,
          is_quellensteuer_subject: e.target.checked,
        }))}
      />
      My income tax is deducted at source by my employer (Quellensteuer)
    </label>
  </div>
)}

{/* Cross-border commuter */}
{formData.nationality_status !== "swiss" && (
  <div className="field-group checkbox-field">
    <label>
      <input
        type="checkbox"
        checked={formData.is_cross_border_commuter}
        onChange={e => setFormData(p => ({
          ...p,
          is_cross_border_commuter: e.target.checked,
        }))}
      />
      I am a cross-border commuter — I live abroad and work in Switzerland
    </label>
  </div>
)}
```

---

#### Step 3 extensions — after the existing `lease_reference_rate_tracked` field block:

```tsx
{/* Lease type */}
{formData.housing_status === "tenant" && (
  <div className="field-group">
    <label htmlFor="lease_type">Lease type</label>
    <select
      id="lease_type"
      value={formData.lease_type ?? ""}
      onChange={e => setFormData(p => ({
        ...p,
        lease_type: e.target.value || undefined,
      }))}
    >
      <option value="">Select…</option>
      {LEASE_TYPE_OPTIONS.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  </div>
)}

{/* Last rent increase year */}
{formData.housing_status === "tenant" && (
  <div className="field-group">
    <label htmlFor="last_rent_increase_year">
      Year of last rent increase <span className="field-optional">(optional)</span>
    </label>
    <input
      id="last_rent_increase_year"
      type="number"
      min={2000}
      max={new Date().getFullYear()}
      placeholder="e.g. 2022"
      value={formData.last_rent_increase_year ?? ""}
      onChange={e => setFormData(p => ({
        ...p,
        last_rent_increase_year: e.target.value ? parseInt(e.target.value) : undefined,
      }))}
    />
  </div>
)}

{/* Tenancy deposit amount */}
{formData.housing_status === "tenant" && (
  <div className="field-group">
    <label htmlFor="tenancy_deposit_chf">
      Rental deposit amount — CHF <span className="field-optional">(optional)</span>
    </label>
    <input
      id="tenancy_deposit_chf"
      type="number"
      min={0}
      placeholder="e.g. 4500"
      value={formData.tenancy_deposit_chf ?? ""}
      onChange={e => setFormData(p => ({
        ...p,
        tenancy_deposit_chf: e.target.value ? parseFloat(e.target.value) : undefined,
      }))}
    />
  </div>
)}
```

---

#### Step 4 extensions — after the existing `recent_life_events` chip section:

Add event chips by extending the chip grid with `EVENT_CHIP_OPTIONS`:
```tsx
{/* Extended event chips */}
<div className="chips-grid">
  {EVENT_CHIP_OPTIONS.map(chip => (
    <button
      key={chip.value}
      type="button"
      className={`chip ${
        formData[chip.value as keyof typeof formData] ? "chip--selected" : ""
      }`}
      onClick={() =>
        setFormData(p => ({
          ...p,
          [chip.value]: !p[chip.value as keyof typeof p],
        }))
      }
    >
      {chip.label}
    </button>
  ))}
</div>

{/* Maternity expected date — shown when recent_life_events includes 'had_child' 
    OR maternity is selected — adapt to however your existing chip toggles work */}

{/* Personal note — final field in Step 4 */}
<div className="field-group" style={{ marginTop: "1.5rem" }}>
  <label htmlFor="personal_note">
    Anything else about your situation?{" "}
    <span className="field-optional">(optional — up to 1,000 characters)</span>
  </label>
  <p className="field-hint">
    For example: dispute with landlord, recent accident at work, unpaid wages,
    permit expiring, employer requesting non-compete signature.
    Helps surface rights you might not know to ask about.
  </p>
  <textarea
    id="personal_note"
    rows={4}
    maxLength={1000}
    placeholder="Describe your situation in your own words…"
    value={formData.personal_note ?? ""}
    onChange={e =>
      setFormData(p => ({
        ...p,
        personal_note: e.target.value || undefined,
      }))
    }
  />
  <span className="char-count">
    {(formData.personal_note ?? "").length} / 1000
  </span>
</div>
```

---

#### New Step 5 — Income & Tax

Add a new step object to the wizard's step array with the following fields:

```tsx
// Step 5: Income & Tax
{
  title: "Income & tax",
  subtitle: "Used to calculate deductions, subsidies, and eligibility thresholds.",
  fields: (
    <>
      <div className="field-group">
        <label htmlFor="gross_income_chf_yearly">
          Annual gross income — CHF <span className="field-optional">(optional)</span>
        </label>
        <p className="field-hint">
          Unlocks tax deduction estimates, health premium reduction, and subsidy eligibility.
        </p>
        <input
          id="gross_income_chf_yearly"
          type="number"
          min={0}
          placeholder="e.g. 95000"
          value={formData.gross_income_chf_yearly ?? ""}
          onChange={e => setFormData(p => ({
            ...p,
            gross_income_chf_yearly: e.target.value ? parseFloat(e.target.value) : undefined,
          }))}
        />
      </div>

      {/* Pillar 3a — hide for retired */}
      {formData.employment_status !== "retired" && (
        <div className="field-group">
          <label htmlFor="pillar_3a_contribution_chf">
            Pillar 3a annual contribution — CHF <span className="field-optional">(optional)</span>
          </label>
          <p className="field-hint">
            Max CHF 7,056 if employed; CHF 35,280 if self-employed without pension fund (2024).
          </p>
          <input
            id="pillar_3a_contribution_chf"
            type="number"
            min={0}
            max={35280}
            placeholder="e.g. 7056"
            value={formData.pillar_3a_contribution_chf ?? ""}
            onChange={e => setFormData(p => ({
              ...p,
              pillar_3a_contribution_chf: e.target.value ? parseFloat(e.target.value) : undefined,
            }))}
          />
        </div>
      )}

      <div className="field-group">
        <label htmlFor="health_insurance_franchise_chf">Health insurance franchise</label>
        <select
          id="health_insurance_franchise_chf"
          value={formData.health_insurance_franchise_chf ?? ""}
          onChange={e => setFormData(p => ({
            ...p,
            health_insurance_franchise_chf: e.target.value ? parseInt(e.target.value) : undefined,
          }))}
        >
          <option value="">Select…</option>
          {FRANCHISE_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      <div className="field-group">
        <label htmlFor="home_office_days_weekly">
          Home office days per week <span className="field-optional">(optional)</span>
        </label>
        <input
          id="home_office_days_weekly"
          type="number"
          min={0}
          max={5}
          placeholder="e.g. 2"
          value={formData.home_office_days_weekly ?? ""}
          onChange={e => setFormData(p => ({
            ...p,
            home_office_days_weekly: e.target.value ? parseInt(e.target.value) : undefined,
          }))}
        />
      </div>

      <div className="field-group">
        <label htmlFor="professional_association_fees_chf">
          Professional association fees — CHF/year <span className="field-optional">(optional)</span>
        </label>
        <p className="field-hint">Trade union, licensing body, or professional society fees.</p>
        <input
          id="professional_association_fees_chf"
          type="number"
          min={0}
          placeholder="e.g. 600"
          value={formData.professional_association_fees_chf ?? ""}
          onChange={e => setFormData(p => ({
            ...p,
            professional_association_fees_chf: e.target.value ? parseFloat(e.target.value) : undefined,
          }))}
        />
      </div>

      {/* Alimony — only for divorced/separated */}
      {(formData.marital_status === "divorced") && (
        <div className="field-group">
          <label htmlFor="alimony_paid_chf_yearly">
            Alimony paid — CHF/year <span className="field-optional">(optional)</span>
          </label>
          <p className="field-hint">Periodic maintenance payments under a divorce decree (DBG Art. 33).</p>
          <input
            id="alimony_paid_chf_yearly"
            type="number"
            min={0}
            placeholder="e.g. 18000"
            value={formData.alimony_paid_chf_yearly ?? ""}
            onChange={e => setFormData(p => ({
              ...p,
              alimony_paid_chf_yearly: e.target.value ? parseFloat(e.target.value) : undefined,
            }))}
          />
        </div>
      )}

      <div className="field-group">
        <label htmlFor="charitable_donations_chf_yearly">
          Charitable donations — CHF/year <span className="field-optional">(optional)</span>
        </label>
        <p className="field-hint">ZEWO-certified organisations. Deductible up to 20% of net income.</p>
        <input
          id="charitable_donations_chf_yearly"
          type="number"
          min={0}
          placeholder="e.g. 2000"
          value={formData.charitable_donations_chf_yearly ?? ""}
          onChange={e => setFormData(p => ({
            ...p,
            charitable_donations_chf_yearly: e.target.value ? parseFloat(e.target.value) : undefined,
          }))}
        />
      </div>
    </>
  ),
}
```

---

#### New Step 6 — Social Security & Disability

```tsx
// Step 6: Social security & disability
{
  title: "Social security",
  subtitle: "Optional — helps identify pension, disability, and unemployment entitlements.",
  fields: (
    <>
      <div className="field-group">
        <label htmlFor="disability_iv_grade">Disability status</label>
        <select
          id="disability_iv_grade"
          value={formData.disability_iv_grade ?? ""}
          onChange={e => setFormData(p => ({
            ...p,
            disability_iv_grade: e.target.value || undefined,
          }))}
        >
          <option value="">Select…</option>
          {DISABILITY_IV_GRADE_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      <div className="field-group">
        <label htmlFor="ahv_contribution_gap_years">
          AHV contribution gap years <span className="field-optional">(optional)</span>
        </label>
        <p className="field-hint">
          Years where you did not contribute to AHV (studied abroad, career break, etc.).
          Each gap year reduces your pension — voluntary payment may be possible.
        </p>
        <input
          id="ahv_contribution_gap_years"
          type="number"
          min={0}
          max={44}
          placeholder="e.g. 3"
          value={formData.ahv_contribution_gap_years ?? ""}
          onChange={e => setFormData(p => ({
            ...p,
            ahv_contribution_gap_years: e.target.value ? parseInt(e.target.value) : undefined,
          }))}
        />
      </div>

      <div className="field-group">
        <label htmlFor="alv_contribution_months_last_2y">
          ALV contribution months in the last 2 years <span className="field-optional">(optional)</span>
        </label>
        <p className="field-hint">
          Months where your employer paid into unemployment insurance.
          12+ months → 260 days of unemployment allowance.
        </p>
        <input
          id="alv_contribution_months_last_2y"
          type="number"
          min={0}
          max={24}
          placeholder="e.g. 18"
          value={formData.alv_contribution_months_last_2y ?? ""}
          onChange={e => setFormData(p => ({
            ...p,
            alv_contribution_months_last_2y: e.target.value ? parseInt(e.target.value) : undefined,
          }))}
        />
      </div>

      <div className="field-group">
        <label htmlFor="bvg_plan_type">Pension fund plan (BVG)</label>
        <select
          id="bvg_plan_type"
          value={formData.bvg_plan_type ?? ""}
          onChange={e => setFormData(p => ({
            ...p,
            bvg_plan_type: e.target.value || undefined,
          }))}
        >
          <option value="">Select…</option>
          {BVG_PLAN_TYPE_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>
    </>
  ),
}
```

### Validation
```bash
cd frontend
npx tsc --noEmit
npx next build
```

### Relevant files
- `frontend/components/profile-wizard/SteppedWizard.tsx` — **primary edit target**
- `frontend/components/profile-wizard/constants.ts` — import source (read-only in this phase)
- `frontend/lib/api-types.ts` — import source (read-only in this phase)

---

## PHASE 2E — VALIDATION GATE (ALL PHASES REQUIRED)
### ⛔ Run last — requires 2A + 2B + 2C + 2D all complete

### What & Why
Re-run the Phase 1 audit script against the updated codebase to confirm the delta is closed,
then run the existing smoke test to confirm no regressions. The benefit count baseline is 12
(confirmed by Phase 1) — the smoke test must not fall below this.

### Done looks like
- `backend/diagnostics/profile_audit.json` `missing_fields` is `[]` when the audit script reruns.
- `benefit_count` is ≥ 12 (no regression from Phase 1 baseline).
- `smoke_test_result` is `"pass"`.
- `python -m pytest backend/ -x -q` exits 0.
- `cd frontend && npx tsc --noEmit && npx next build` exits 0.

### Out of scope
- Do NOT add entitlement seeds to inflate the benefit count.
- Do NOT lower the ≥ 12 threshold.
- Do NOT mock the LLM response to make the smoke test pass.

### Done looks like (technical guardrails)
```bash
# Step 1 — Rerun the Phase 1 audit script
python backend/diagnostics/run_audit.py   # or however Phase 1 was invoked

# Step 2 — Confirm missing_fields is empty
python - <<'EOF'
import json
d = json.load(open("backend/diagnostics/profile_audit.json"))
assert d["missing_fields"] == [], \
    f"Still missing: {d['missing_fields']}"
assert d["smoke_test_result"] == "pass", \
    f"Smoke test failed: {d.get('smoke_test_result')}"
assert d["benefit_count"] >= 12, \
    f"Benefit count regression: {d['benefit_count']} < 12"
print(f"missing_fields: [] ✓")
print(f"smoke_test_result: pass ✓")
print(f"benefit_count: {d['benefit_count']} (≥ 12) ✓")
print("PHASE 2E GATE: PASSED — Sprint complete")
EOF

# Step 3 — Backend test suite
python -m pytest backend/ -x -q

# Step 4 — Frontend build
cd frontend && npx tsc --noEmit && npx next build
```

### Steps
1. Re-run the Phase 1 audit script (use the exact command that produced
   `backend/diagnostics/profile_audit.json` in Phase 1).
2. Run the gate script above.
3. If `missing_fields` is non-empty, return to Phase 2A and add the remaining fields.
4. If `benefit_count` < 12, do NOT add seeds — investigate whether the scan service is
   failing to load the updated model and fix the import, not the threshold.
5. If the frontend build fails, return to Phase 2D and fix the TypeScript error.

### Validation
```bash
python - <<'EOF'
import json
d = json.load(open("backend/diagnostics/profile_audit.json"))
assert d["missing_fields"] == []
assert d["smoke_test_result"] == "pass"
assert d["benefit_count"] >= 12
print("SPRINT COMPLETE")
EOF
```

### Relevant files
- `backend/diagnostics/profile_audit.json` — gate artifact (read + overwritten by re-run)
- `backend/diagnostics/run_audit.py` — audit script from Phase 1 (run but do not modify)

---

## PHASE DEPENDENCY GRAPH

```
Phase 2A (Backend Pydantic model) ──────────────────────► Phase 2C (api-types regen)
                                                                    │
Phase 2B (Frontend constants) ──────────────────────────────────────┤
                                                                    ▼
                                                         Phase 2D (Wizard UI)
                                                                    │
                                              ┌─────────────────────┤
                                              │                     │
                                        Phase 2A               Phase 2B
                                              │                     │
                                              └──────────┬──────────┘
                                                         ▼
                                              Phase 2E (Validation gate)
```

---

## GLOBAL FORBIDDEN LIST — applies to all Phase 2 sub-phases

- Do NOT use `eval()` anywhere.
- Do NOT add new Python or npm packages.
- Do NOT delete or rename any field that already exists on `ContextProfile`.
- Do NOT add `children_ages` — it is not in the 26 confirmed missing fields.
- Do NOT add new entitlement seed JSON files (Phase 3 sprint).
- Do NOT change the `/scan/stream` response format or endpoint signature.
- Do NOT introduce `any` TypeScript types to suppress errors.
- Do NOT hardcode option strings in `SteppedWizard.tsx` — all options come from `constants.ts`.
- Do NOT lower the benefit_count threshold to make the validation gate pass.
- Do NOT log or persist `personal_note` to any database or log file.
- Do NOT add new wizard validation schemas (Zod or other) in this phase.
- Do NOT modify `backend/fixtures/luis_profile.json`.
