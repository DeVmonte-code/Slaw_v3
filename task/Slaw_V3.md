# Slaw v3 — Phase 3 Sprint: Profile Interpretation Pass + Seed Expansion
## Replit Agent Prompt

> **Why this sprint exists:**
> A live scan of a real test profile (BE canton, student, B permit, divorced tenant) returned
> only 3 benefits — all tenancy-only. The audit confirmed two root causes:
> (1) Zero seeds exist for students, B-permit holders, or cross-domain personas.
> (2) The `personal_note` field is received by the backend but never read by the scan pipeline.
> This sprint fixes both via a Profile Interpretation Pass (PIP) + 8 new entitlement seeds.
>
> **Execution order:**
> Phase 1 (DIAGNOSTIC) is blocking — do not start 2A or 2B until it completes.
> Phase 2A and 2B run in parallel (different files). Phase 3 requires 2A complete.
> Phase 4 requires Phase 3. Phase 5 requires Phase 3. Phase 6 requires all prior phases.

---

## PHASE 1 — DIAGNOSTIC (BLOCKING)

### What & Why
Audit `engine/scan.py` and `engine/trigger.py` to confirm the exact insertion points for the
PIP, verify `personal_note` is not currently read during scan execution, and identify the
exact line where `evaluate_trigger(expr, profile)` is called in the trigger loop.
Output a JSON file so Phases 2A–5 have concrete line references.

### Done looks like
- `backend/diagnostics/pip_audit.json` exists and is valid JSON.
- JSON contains keys: `scan_py_trigger_loop_line`, `personal_note_read_in_scan`,
  `resolve_handles_dict`, `entitlement_count`, `student_seed_count`.
- `personal_note_read_in_scan` is `false`.
- `resolve_handles_dict` is `true` (confirms `_resolve()` already handles dict input).
- `student_seed_count` is `0`.
- `entitlement_count` is `15`.

### Out of scope
- Do NOT modify any source file.
- Do NOT run the scan pipeline.
- Do NOT touch the frontend.

### Done looks like (technical guardrails)
```bash
python - <<'EOF'
import json, sys
d = json.load(open("backend/diagnostics/pip_audit.json"))
required = {
    "scan_py_trigger_loop_line", "personal_note_read_in_scan",
    "resolve_handles_dict", "entitlement_count", "student_seed_count"
}
assert required.issubset(d.keys()), f"Missing keys: {required - d.keys()}"
assert d["personal_note_read_in_scan"] == False, "personal_note should NOT be read yet"
assert d["resolve_handles_dict"] == True,  "_resolve() must already handle dicts"
assert d["student_seed_count"] == 0,       "No student seeds should exist yet"
assert d["entitlement_count"] == 15,       "Baseline seed count must be 15"
print("PHASE 1 GATE: PASSED")
EOF
```

### Steps
1. Read `backend/src/swiss_legal_api/engine/scan.py`. Find the line where
   `evaluate_trigger` is called inside the main entitlement loop.
   Record this as `scan_py_trigger_loop_line` (integer).

2. Search `scan.py` for any reference to `personal_note`. If absent, set
   `personal_note_read_in_scan = false`.

3. Read `backend/src/swiss_legal_api/engine/trigger.py`. Locate `_resolve()`.
   Confirm it contains `if isinstance(obj, dict): obj = obj.get(key)`.
   Set `resolve_handles_dict = true` if present, else `false`.

4. Count entitlements in `backend/seed/entitlements.json`. Set `entitlement_count`.

5. Count seeds where the trigger references `"student"` in any `eq` or `in` operator.
   Set `student_seed_count`.

6. Write `backend/diagnostics/pip_audit.json`.

### Validation
```bash
python - <<'EOF'
import json
d = json.load(open("backend/diagnostics/pip_audit.json"))
print(json.dumps(d, indent=2))
assert d["personal_note_read_in_scan"] == False
assert d["resolve_handles_dict"] == True
print("PHASE 1 GATE: PASSED")
EOF
```

### Relevant files
- `backend/src/swiss_legal_api/engine/scan.py` — read-only
- `backend/src/swiss_legal_api/engine/trigger.py` — read-only
- `backend/seed/entitlements.json` — read-only
- `backend/diagnostics/pip_audit.json` — CREATE this file

---

## PHASE 2A — PROFILE INTERPRETATION PASS (scan.py)
### ⛔ Blocking for Phase 3

### What & Why
Insert the Profile Interpretation Pass (PIP) into `engine/scan.py`. The PIP is a single LLM
call that runs ONCE at scan start, reads the entire profile including `personal_note` and
`free_text_narrative`, and outputs a flat JSON dict of inferred signals. These signals are
merged with `profile.model_dump()` into a `merged_context` dict. The existing trigger loop
is changed to pass `merged_context` instead of `profile` to `evaluate_trigger()`.

`trigger.py._resolve()` already handles dict input — it will NOT be modified.

If the PIP fails, times out, or returns invalid JSON, the scan continues with an empty signal
dict `{}` — the fallback must never crash the pipeline.

### Done looks like
- `engine/scan.py` contains a function `interpret_profile_pip(profile, client)` that:
  - Makes one Claude API call using the `claude-sonnet-4-20250514` model.
  - Has a 15-second timeout.
  - Returns a `dict[str, Any]` — never raises an exception.
  - Returns `{}` on any failure.
- The main scan function merges PIP output: `merged_context = {**profile.model_dump(), **pip_signals}`.
- The trigger loop passes `merged_context` to `evaluate_trigger()`, not `profile`.
- `python -m pytest backend/tests/ -x -q -k "not integration"` exits 0.

### Out of scope
- Do NOT modify `trigger.py`.
- Do NOT modify `trigger_dsl.py`.
- Do NOT add new seeds in this phase.
- Do NOT add a new API endpoint.
- Do NOT change the streaming response format.
- Do NOT log or persist `personal_note` content.
- Do NOT modify any frontend file.

### Done looks like (technical guardrails)
```bash
# Confirm PIP function exists
python - <<'EOF'
import ast, sys
src = open("backend/src/swiss_legal_api/engine/scan.py").read()
assert "interpret_profile_pip" in src, "PIP function missing from scan.py"
assert "merged_context" in src, "merged_context merge missing"
assert "model_dump" in src, "profile.model_dump() call missing"
assert "personal_note" in src, "personal_note not referenced in scan.py"

# Confirm trigger.py was NOT modified
import subprocess
result = subprocess.run(
    ["git", "diff", "--name-only", "HEAD"],
    capture_output=True, text=True
)
modified = result.stdout.strip().split("\n")
assert not any("trigger.py" in f for f in modified), \
    "trigger.py must NOT be modified"

print("PHASE 2A GATE: PASSED")
EOF

python -m pytest backend/tests/ -x -q -k "not integration"
```

### Steps

1. Open `backend/src/swiss_legal_api/engine/scan.py`.

2. Add the PIP imports at the top of the file (after existing imports):
```python
import asyncio
import json as _json
from typing import Any
```

3. Add the `PIP_SIGNAL_SCHEMA` constant (the canonical signal vocabulary the PIP may output):
```python
# Canonical inferred-signal keys. Seeds may reference these in trigger DSL.
PIP_SIGNAL_SCHEMA: dict[str, str] = {
    "permit_type_inferred":          "string — B / C / L / G / none (from personal_note)",
    "is_working_student":            "bool — employment_status==student AND weekly_hours>=8",
    "is_part_time_worker":           "bool — weekly_hours > 0 AND weekly_hours < 35",
    "has_foreign_permit":            "bool — any non-Swiss permit inferred",
    "is_b_permit_annual_renewal":    "bool — B permit requiring annual renewal",
    "wants_registered_partnership":  "bool — user signals intent to enter registered partnership",
    "is_transitioning_marital_status": "bool — marital status change mentioned in note",
    "ahv_contribution_obligation":   "bool — working student with AHV deduction obligation",
    "is_quellensteuer_liable":       "bool — non-Swiss permit subject to source tax",
    "has_named_employer":            "bool — personal_note or narrative mentions employer",
    "permit_renewal_imminent":       "bool — permit expiry or renewal mentioned in note",
    "registered_partnership_right":  "bool — AIG Art. 42 family reunification via partnership",
}
```

4. Add the `interpret_profile_pip` function:
```python
async def interpret_profile_pip(
    profile: "ContextProfile",
    client: Any,
) -> dict[str, Any]:
    """
    Single LLM call. Reads the entire profile holistically — structured fields
    AND personal_note / free_text_narrative — and returns a flat dict of
    inferred boolean/string signals.

    NEVER raises. Returns {} on any failure so the scan pipeline continues.
    """
    system = (
        "You are a Swiss legal signal extractor. "
        "You receive a user profile as JSON and must infer legal status signals "
        "that are not explicitly captured by structured fields. "
        "You MUST respond with ONLY a valid JSON object — no explanation, no markdown, "
        "no prose before or after. "
        "Keys must come from the provided schema. Values must be bool or string. "
        "If you cannot infer a signal with confidence, omit it. "
        "NEVER invent facts not supported by the profile."
    )

    schema_str = _json.dumps(PIP_SIGNAL_SCHEMA, ensure_ascii=False, indent=2)
    profile_str = profile.model_dump_json(indent=2)

    user_msg = (
        f"Signal schema (keys you may output):\n{schema_str}\n\n"
        f"User profile:\n{profile_str}\n\n"
        "Return ONLY a JSON object of inferred signals. "
        "Pay special attention to personal_note and free_text_narrative fields."
    )

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            ),
            timeout=15.0,
        )
        raw = response.content[0].text.strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        signals: dict[str, Any] = _json.loads(raw)
        # Validate: only allow schema keys
        valid = {k: v for k, v in signals.items() if k in PIP_SIGNAL_SCHEMA}
        return valid
    except Exception:
        return {}
```

5. In the main scan function (wherever it currently calls `evaluate_trigger(expr, profile)`),
   insert the PIP call BEFORE the trigger loop and build `merged_context`:

```python
# --- Profile Interpretation Pass ---
pip_signals: dict[str, Any] = await interpret_profile_pip(profile, client)
merged_context: dict[str, Any] = {**profile.model_dump(), **pip_signals}
# --- End PIP ---
```

6. Change every call from:
```python
evaluate_trigger(entitlement.trigger, profile)
```
to:
```python
evaluate_trigger(entitlement.trigger, merged_context)
```

   Use the exact line number from `pip_audit.json` (`scan_py_trigger_loop_line`) to locate it.
   If `evaluate_trigger` is called in multiple places within the same scan function, update all.

7. Run the unit tests to confirm no regressions:
```bash
python -m pytest backend/tests/ -x -q -k "not integration"
```

### Validation
```bash
python -m pytest backend/tests/ -x -q -k "not integration"
```

### Relevant files
- `backend/src/swiss_legal_api/engine/scan.py` — **primary edit target**
- `backend/src/swiss_legal_api/engine/trigger.py` — READ ONLY — do not touch
- `backend/diagnostics/pip_audit.json` — read for line numbers

---

## PHASE 2B — PIP PROMPT CONSTANTS (prompt/ directory)
### ✅ Parallel with Phase 2A

### What & Why
Extract the PIP system prompt and schema into a dedicated file under `backend/prompt/` so
they can be versioned, reviewed, and improved independently of `scan.py` logic.
This phase writes the file only — it does not wire it into scan.py (Phase 2A handles wiring).

### Done looks like
- `backend/prompt/pip_system_prompt.py` exists.
- It exports `PIP_SYSTEM_PROMPT: str` and `PIP_SIGNAL_SCHEMA: dict[str, str]`.
- `python -c "from backend.prompt.pip_system_prompt import PIP_SYSTEM_PROMPT, PIP_SIGNAL_SCHEMA; print('OK')"` exits 0.

### Out of scope
- Do NOT modify `scan.py` in this phase.
- Do NOT modify any seed file.
- Do NOT touch the frontend.

### Done looks like (technical guardrails)
```bash
python - <<'EOF'
import sys
sys.path.insert(0, "backend")
from prompt.pip_system_prompt import PIP_SYSTEM_PROMPT, PIP_SIGNAL_SCHEMA
assert isinstance(PIP_SYSTEM_PROMPT, str) and len(PIP_SYSTEM_PROMPT) > 100
assert isinstance(PIP_SIGNAL_SCHEMA, dict) and len(PIP_SIGNAL_SCHEMA) >= 10
assert "permit_type_inferred" in PIP_SIGNAL_SCHEMA
assert "is_working_student" in PIP_SIGNAL_SCHEMA
assert "wants_registered_partnership" in PIP_SIGNAL_SCHEMA
print("PHASE 2B GATE: PASSED")
EOF
```

### Steps
Create `backend/prompt/pip_system_prompt.py` with exactly this content:

```python
"""
Profile Interpretation Pass — system prompt and signal schema.
Versioned separately from scan.py so it can be improved without
touching pipeline logic.
"""

PIP_SYSTEM_PROMPT: str = (
    "You are a Swiss legal signal extractor operating within the Slaw rights-discovery system. "
    "You receive a complete ContextProfile as JSON — structured fields plus any free-text "
    "narrative the user provided. "
    "\n\n"
    "Your task: infer legal status signals that are not explicitly captured by structured "
    "form fields but are clearly implied by the profile as a whole. "
    "\n\n"
    "Rules:\n"
    "1. Respond with ONLY a valid JSON object — no markdown fences, no explanation, no prose.\n"
    "2. Use only keys from the provided signal schema. Never invent new keys.\n"
    "3. Values must be boolean (true/false) or string literals from the schema description.\n"
    "4. Omit a key entirely if you cannot infer it with reasonable confidence.\n"
    "5. Pay special attention to `personal_note` and `free_text_narrative` — these are the "
    "primary sources of signals not captured by structured fields.\n"
    "6. Do not reproduce the profile back. Output only the inferred signals dict.\n"
    "7. Never invent facts not supported by the profile content."
)

PIP_SIGNAL_SCHEMA: dict[str, str] = {
    "permit_type_inferred": (
        "string — inferred permit type from personal_note: B / C / L / G / F / N / none"
    ),
    "is_working_student": (
        "bool — true when employment_status=student AND weekly_hours >= 8"
    ),
    "is_part_time_worker": (
        "bool — true when weekly_hours > 0 AND weekly_hours < 35"
    ),
    "has_foreign_permit": (
        "bool — true when any non-Swiss residence permit is mentioned or inferred"
    ),
    "is_b_permit_annual_renewal": (
        "bool — true when B permit requiring annual renewal is mentioned in personal_note"
    ),
    "wants_registered_partnership": (
        "bool — true when user signals intent to enter a registered partnership (eingetragene Partnerschaft)"
    ),
    "is_transitioning_marital_status": (
        "bool — true when a change in civil status (marriage, partnership, divorce) is described"
    ),
    "ahv_contribution_obligation": (
        "bool — true when user is a working student with AHV deduction obligation (weekly_hours >= 8)"
    ),
    "is_quellensteuer_liable": (
        "bool — true when profile implies non-Swiss permit subject to Quellensteuer (source tax)"
    ),
    "has_named_employer": (
        "bool — true when personal_note or narrative mentions a specific employer"
    ),
    "permit_renewal_imminent": (
        "bool — true when permit expiry or renewal process is mentioned in personal_note"
    ),
    "registered_partnership_permit_right": (
        "bool — true when AIG Art. 42 family reunification via registered partnership is applicable"
    ),
}
```

### Validation
```bash
python - <<'EOF'
import sys
sys.path.insert(0, "backend")
from prompt.pip_system_prompt import PIP_SYSTEM_PROMPT, PIP_SIGNAL_SCHEMA
assert "permit_type_inferred" in PIP_SIGNAL_SCHEMA
print(f"Schema keys: {len(PIP_SIGNAL_SCHEMA)}")
print("PHASE 2B GATE: PASSED")
EOF
```

### Relevant files
- `backend/prompt/pip_system_prompt.py` — **CREATE this file**

---

## PHASE 3 — 8 NEW ENTITLEMENT SEEDS
### ⚠️ Requires Phase 2A complete (signals must exist before seeds reference them)

### What & Why
Add 8 new entitlement seeds to `backend/seed/entitlements.json`. These seeds cover the
persona categories exposed by the test profile audit: working students, B-permit holders,
foreign nationals navigating permit transitions, divorced users, and health-premium reduction.
Seeds reference PIP-inferred signals (`permit_type_inferred`, `is_working_student`, etc.)
which are available in `merged_context` after Phase 2A.

### Done looks like
- `backend/seed/entitlements.json` contains 23 seeds (15 existing + 8 new).
- All 8 new seed IDs are present in the file.
- The JSON parses without error.
- `python -m pytest backend/tests/ -x -q -k "not integration"` exits 0.

### Out of scope
- Do NOT modify any existing seed trigger conditions.
- Do NOT modify `scan.py`, `trigger.py`, or any schema file.
- Do NOT touch the frontend.
- Do NOT add more than 8 seeds in this phase — additional seeds are a separate sprint.

### Done looks like (technical guardrails)
```bash
python - <<'EOF'
import json
seeds = json.load(open("backend/seed/entitlements.json"))
assert len(seeds) == 23, f"Expected 23 seeds, found {len(seeds)}"
new_ids = {
    "student_b_permit_renewal_right",
    "working_student_ahv_partial_obligation",
    "health_premium_reduction_ipv",
    "quellensteuer_correction_inferred_permit",
    "registered_partnership_permit_right",
    "divorced_alimony_deduction",
    "student_professional_training_deduction",
    "tenant_deposit_cap_protection",
}
found = {s["id"] for s in seeds}
missing = new_ids - found
assert not missing, f"Missing seed IDs: {missing}"
print(f"All 8 new seeds present. Total: {len(seeds)}")
print("PHASE 3 GATE: PASSED")
EOF
```

### Steps
Append the following 8 objects to the JSON array in `backend/seed/entitlements.json`.
Do NOT remove or modify any existing object. Add them at the end of the array.

```json
  {
    "id": "student_b_permit_renewal_right",
    "title": {
      "de": "Aufenthaltsbewilligung B – Verlängerungsrecht für Studierende",
      "en": "B Permit Renewal Right for Students"
    },
    "category": "social_security",
    "jurisdiction": "CH",
    "source_citations": [
      {
        "sr_number": "142.20",
        "article": "22",
        "paragraph": "1",
        "canton": "CH",
        "language": "de",
        "quote_under_15_words": "Ausländerinnen und Ausländer können zur Aus- und Weiterbildung zugelassen werden"
      }
    ],
    "trigger": {
      "all": [
        {"eq": ["employment_status", "student"]},
        {"any": [
          {"eq": ["permit_type", "B"]},
          {"eq": ["permit_type_inferred", "B"]}
        ]}
      ]
    },
    "estimated_value_chf": {"min": 0, "max": 500, "per": "year"},
    "required_action": "cantonal_application",
    "time_limit_days": null,
    "confidence_floor": 0.6
  },
  {
    "id": "working_student_ahv_partial_obligation",
    "title": {
      "de": "AHV-Beitragspflicht für arbeitende Studierende",
      "en": "AHV Contribution Obligation for Working Students"
    },
    "category": "social_security",
    "jurisdiction": "CH",
    "source_citations": [
      {
        "sr_number": "831.10",
        "article": "5",
        "paragraph": "1",
        "canton": "CH",
        "language": "de",
        "quote_under_15_words": "Vom Einkommen aus unselbständiger Erwerbstätigkeit wird ein Beitrag erhoben"
      }
    ],
    "trigger": {
      "any": [
        {"eq": ["is_working_student", true]},
        {
          "all": [
            {"eq": ["employment_status", "student"]},
            {"gte": ["weekly_hours", 8]}
          ]
        }
      ]
    },
    "estimated_value_chf": {"min": 0, "max": 1500, "per": "year"},
    "required_action": "employer_request",
    "time_limit_days": null,
    "confidence_floor": 0.6
  },
  {
    "id": "health_premium_reduction_ipv",
    "title": {
      "de": "Individuelle Prämienverbilligung (IPV)",
      "en": "Individual Health Insurance Premium Reduction (IPV)"
    },
    "category": "social_security",
    "jurisdiction": "CH",
    "source_citations": [
      {
        "sr_number": "832.10",
        "article": "65",
        "paragraph": "1",
        "canton": "CH",
        "language": "de",
        "quote_under_15_words": "Versicherte in bescheidenen wirtschaftlichen Verhältnissen haben Anspruch auf Prämienverbilligung"
      }
    ],
    "trigger": {
      "any": [
        {"lte": ["gross_income_chf_yearly", 75000]},
        {
          "all": [
            {"exists": "gross_income_chf_yearly"},
            {"lte": ["gross_income_chf_yearly", 75000]}
          ]
        },
        {"eq": ["employment_status", "student"]},
        {"eq": ["employment_status", "unemployed"]}
      ]
    },
    "estimated_value_chf": {"min": 500, "max": 9000, "per": "year"},
    "required_action": "cantonal_application",
    "time_limit_days": null,
    "confidence_floor": 0.6
  },
  {
    "id": "quellensteuer_correction_inferred_permit",
    "title": {
      "de": "Nachträgliche Quellensteuerkorrektur (Permit aus Profil abgeleitet)",
      "en": "Quellensteuer Subsequent Correction (Permit Inferred from Profile)"
    },
    "category": "tax_deduction",
    "jurisdiction": "CH",
    "source_citations": [
      {
        "sr_number": "642.11",
        "article": "99a",
        "paragraph": "1",
        "canton": "CH",
        "language": "de",
        "quote_under_15_words": "Personen, die nach Artikel 91 der Quellensteuer unterliegen, können für jede Steuerperiode"
      }
    ],
    "trigger": {
      "any": [
        {
          "all": [
            {"eq": ["permit_type", "B"]},
            {"not": {"eq": ["nationality_status", "swiss"]}}
          ]
        },
        {
          "all": [
            {"eq": ["permit_type_inferred", "B"]},
            {"not": {"eq": ["nationality_status", "swiss"]}}
          ]
        },
        {"eq": ["is_quellensteuer_liable", true]}
      ]
    },
    "estimated_value_chf": {"min": 500, "max": 5000, "per": "year"},
    "required_action": "cantonal_application",
    "time_limit_days": null,
    "confidence_floor": 0.6
  },
  {
    "id": "registered_partnership_permit_right",
    "title": {
      "de": "Aufenthaltsrecht bei eingetragener Partnerschaft (AIG Art. 42/43)",
      "en": "Residence Right via Registered Partnership (AIG Art. 42/43)"
    },
    "category": "social_security",
    "jurisdiction": "CH",
    "source_citations": [
      {
        "sr_number": "142.20",
        "article": "42",
        "paragraph": "1",
        "canton": "CH",
        "language": "de",
        "quote_under_15_words": "Ausländische Ehegatten und Kinder von Schweizerinnen und Schweizern"
      }
    ],
    "trigger": {
      "any": [
        {"eq": ["wants_registered_partnership", true]},
        {"eq": ["registered_partnership_permit_right", true]},
        {"eq": ["marital_status", "registered_partnership"]}
      ]
    },
    "estimated_value_chf": {"min": 0, "max": 3000, "per": "one_time"},
    "required_action": "cantonal_application",
    "time_limit_days": null,
    "confidence_floor": 0.6
  },
  {
    "id": "divorced_alimony_deduction",
    "title": {
      "de": "Unterhaltsabzug für Geschiedene (DBG Art. 33 lit. c)",
      "en": "Alimony Deduction for Divorced Persons (DBG Art. 33 lit. c)"
    },
    "category": "tax_deduction",
    "jurisdiction": "CH",
    "source_citations": [
      {
        "sr_number": "642.11",
        "article": "33",
        "paragraph": "1",
        "canton": "CH",
        "language": "de",
        "quote_under_15_words": "die Unterhaltsleistungen an den geschiedenen oder getrennt lebenden Ehegatten"
      }
    ],
    "trigger": {
      "all": [
        {"eq": ["marital_status", "divorced"]},
        {"exists": "alimony_paid_chf_yearly"},
        {"gte": ["alimony_paid_chf_yearly", 1]}
      ]
    },
    "estimated_value_chf": {"min": 1000, "max": 30000, "per": "year"},
    "required_action": "tax_declaration_field",
    "time_limit_days": null,
    "confidence_floor": 0.6
  },
  {
    "id": "student_professional_training_deduction",
    "title": {
      "de": "Berufsausbildungskosten-Abzug für Studierende (DBG Art. 33 lit. j)",
      "en": "Professional Training Cost Deduction for Students (DBG Art. 33 lit. j)"
    },
    "category": "tax_deduction",
    "jurisdiction": "CH",
    "source_citations": [
      {
        "sr_number": "642.11",
        "article": "33",
        "paragraph": "1",
        "canton": "CH",
        "language": "de",
        "quote_under_15_words": "die Kosten der berufsorientierten Aus- und Weiterbildung, einschliesslich der Umschulungskosten"
      }
    ],
    "trigger": {
      "all": [
        {"eq": ["employment_status", "student"]},
        {"gte": ["weekly_hours", 8]}
      ]
    },
    "estimated_value_chf": {"min": 500, "max": 12000, "per": "year"},
    "required_action": "tax_declaration_field",
    "time_limit_days": null,
    "confidence_floor": 0.6
  },
  {
    "id": "tenant_deposit_cap_protection",
    "title": {
      "de": "Mietkautionsbegrenzung – Rückforderungsrecht bei Überziehung (OR Art. 257e)",
      "en": "Rental Deposit Cap Protection – Right to Claim Excess (OR Art. 257e)"
    },
    "category": "tenancy_right",
    "jurisdiction": "CH",
    "source_citations": [
      {
        "sr_number": "220",
        "article": "257e",
        "paragraph": "1",
        "canton": "CH",
        "language": "de",
        "quote_under_15_words": "Die Sicherheit darf höchstens drei Monatsmieten betragen"
      }
    ],
    "trigger": {
      "all": [
        {"eq": ["housing_status", "tenant"]},
        {"exists": "tenancy_deposit_chf"},
        {"gte": ["tenancy_deposit_chf", 1]}
      ]
    },
    "estimated_value_chf": {"min": 0, "max": 5000, "per": "one_time"},
    "required_action": "claim_letter_to_landlord",
    "time_limit_days": null,
    "confidence_floor": 0.6
  }
```

### Validation
```bash
python - <<'EOF'
import json
seeds = json.load(open("backend/seed/entitlements.json"))
assert len(seeds) == 23, f"Expected 23, got {len(seeds)}"
ids = {s["id"] for s in seeds}
required_new = {
    "student_b_permit_renewal_right",
    "working_student_ahv_partial_obligation",
    "health_premium_reduction_ipv",
    "quellensteuer_correction_inferred_permit",
    "registered_partnership_permit_right",
    "divorced_alimony_deduction",
    "student_professional_training_deduction",
    "tenant_deposit_cap_protection",
}
missing = required_new - ids
assert not missing, f"Missing: {missing}"
print("PHASE 3 GATE: PASSED — 23 seeds, 8 new")
EOF
```

### Relevant files
- `backend/seed/entitlements.json` — **primary edit target** (append only)

---

## PHASE 4 — FIX EXISTING TRIGGER GAPS (2 seeds)
### ⚠️ Requires Phase 3 complete

### What & Why
Two existing seeds incorrectly exclude students who would qualify:
- `commuting_cost_deduction` requires `employee_full_time / employee_part_time / self_employed`
  but DBG Art. 26 applies to students in professional training commuting to a workplace.
- `professional_training_deduction` has the same exclusion — DBG Art. 33 lit. j applies to
  all persons in professional training, not only employees.
Both triggers need `"student"` added to their `in` operator value lists.

### Done looks like
- `commuting_cost_deduction` trigger includes `"student"` in its `in` operator.
- `professional_training_deduction` trigger includes `"student"` in its `in` operator.
- All other existing seed fields are unchanged.
- `python -m pytest backend/tests/ -x -q -k "not integration"` exits 0.

### Out of scope
- Do NOT modify any other seed trigger.
- Do NOT modify `scan.py`, `trigger.py`, or schema files.
- Do NOT touch the frontend.

### Done looks like (technical guardrails)
```bash
python - <<'EOF'
import json
seeds = {s["id"]: s for s in json.load(open("backend/seed/entitlements.json"))}

# commuting_cost_deduction
commute = seeds["commuting_cost_deduction"]
in_vals = commute["trigger"]["all"][0]["in"][1]
assert "student" in in_vals, "student missing from commuting_cost_deduction"

# professional_training_deduction
training = seeds["professional_training_deduction"]
# It may have a single 'all' with one 'in' clause
src = json.dumps(training["trigger"])
assert "student" in src, "student missing from professional_training_deduction"

print("PHASE 4 GATE: PASSED")
EOF
```

### Steps
1. Open `backend/seed/entitlements.json`.

2. Find `commuting_cost_deduction`. Its current trigger:
```json
{"in": ["employment_status", ["employee_full_time", "employee_part_time", "self_employed"]]}
```
Change to:
```json
{"in": ["employment_status", ["employee_full_time", "employee_part_time", "self_employed", "student"]]}
```

3. Find `professional_training_deduction`. Its current trigger:
```json
{"in": ["employment_status", ["employee_full_time", "employee_part_time", "self_employed"]]}
```
Change to:
```json
{"in": ["employment_status", ["employee_full_time", "employee_part_time", "self_employed", "student"]]}
```

4. Verify JSON is valid: `python -c "import json; json.load(open('backend/seed/entitlements.json')); print('valid')"`.

### Validation
```bash
python -c "import json; json.load(open('backend/seed/entitlements.json')); print('JSON valid')"
python -m pytest backend/tests/ -x -q -k "not integration"
```

### Relevant files
- `backend/seed/entitlements.json` — **edit 2 existing seeds only**

---

## PHASE 5 — INTEGRATION TEST WITH LIVE TEST PROFILE
### ⛔ Requires ALL prior phases complete (1, 2A, 2B, 3, 4)

### What & Why
Run the exact profile from the May 5 test session through the full pipeline and assert
that ≥ 7 distinct benefits are returned at confidence ≥ 0.6. The baseline was 3 benefits.
This is the acceptance gate for the entire sprint.

The test profile represents: BE canton, student, 15h/week, 3km commute, tenant since 2019,
CHF 730/month rent, divorced, B permit (in personal note), wants registered partnership.

### Done looks like
- The integration test runs to completion without error.
- ≥ 7 benefit IDs are returned with confidence ≥ 0.6.
- The result includes at least 3 of these 5 sentinel IDs:
  - `rent_reduction_reference_rate`
  - `health_premium_reduction_ipv`
  - `student_professional_training_deduction`
  - `quellensteuer_correction_inferred_permit`
  - `student_b_permit_renewal_right`

### Out of scope
- Do NOT mock the LLM response.
- Do NOT lower the ≥ 7 threshold.
- Do NOT add seeds to inflate the count artificially.
- Do NOT modify any prior phase file to make this pass.

### Done looks like (technical guardrails)
```bash
python -m pytest backend/tests/test_phase3_integration.py -v -s
```

### Steps
Create `backend/tests/test_phase3_integration.py`:

```python
"""
Phase 3 integration test — live scan of the May 5 test profile.
Requires a running Anthropic API key in environment.
Marked as integration to allow skipping in unit test runs.
"""
import asyncio
import os
import pytest

from backend.src.swiss_legal_api.schemas.context_profile import ContextProfile

# Skip if no API key present
pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — integration test skipped"
)

MAY5_TEST_PROFILE = ContextProfile(
    canton="BE",
    employment_status="student",
    employment_start_year=2018,
    weekly_hours=15,
    commute_km_daily=3,
    housing_status="tenant",
    rental_start_year=2019,
    rent_chf_monthly=730,
    lease_reference_rate_tracked=True,
    lease_type="indefinite",
    marital_status="divorced",
    household_size=3,
    children_count=0,
    has_third_pillar=True,
    third_pillar_chf_this_year=300,
    nationality_status="eu_efta",   # Non-Swiss — B permit implied
    permit_type="B",                 # Set explicitly for this test
    personal_note=(
        "I am a student that works here and have to renovate the B permit every year "
        "but I want to change my legal status from student to a registered partnership"
    ),
)

SENTINEL_IDS = {
    "rent_reduction_reference_rate",
    "health_premium_reduction_ipv",
    "student_professional_training_deduction",
    "quellensteuer_correction_inferred_permit",
    "student_b_permit_renewal_right",
}


def test_may5_profile_returns_seven_or_more_benefits():
    """
    The May 5 test profile must return ≥ 7 benefits with confidence ≥ 0.6.
    Baseline before this sprint was 3 (tenancy only).
    """
    # Import the scan runner — adjust import path to match actual module
    from backend.src.swiss_legal_api.engine.scan import run_scan  # adjust if needed

    results = asyncio.run(run_scan(MAY5_TEST_PROFILE))

    passing = [r for r in results if r.get("confidence", 0) >= 0.6]
    benefit_ids = {r["entitlement_id"] for r in passing}

    # Check sentinel presence
    found_sentinels = SENTINEL_IDS & benefit_ids
    assert len(found_sentinels) >= 3, (
        f"Expected ≥ 3 sentinel IDs in results, found: {found_sentinels}\n"
        f"All returned IDs: {benefit_ids}"
    )

    # Check total count
    assert len(benefit_ids) >= 7, (
        f"Expected ≥ 7 benefits, got {len(benefit_ids)}: {benefit_ids}"
    )

    print(f"\n✓ {len(benefit_ids)} benefits returned")
    print(f"✓ Sentinels found: {found_sentinels}")
    print(f"✓ All IDs: {benefit_ids}")
```

Run:
```bash
python -m pytest backend/tests/test_phase3_integration.py -v -s
```

If `run_scan` is not the correct function name or import path, check `engine/scan.py` for
the correct entry point and update the import line. Do NOT change the test logic.

### Validation
```bash
python -m pytest backend/tests/test_phase3_integration.py -v -s
```

### Relevant files
- `backend/tests/test_phase3_integration.py` — **CREATE this file**
- `backend/src/swiss_legal_api/engine/scan.py` — read-only reference for import path
- `backend/seed/entitlements.json` — read-only reference

---

## PHASE DEPENDENCY GRAPH

```
Phase 1 — DIAGNOSTIC (blocking)
    │
    ├──► Phase 2A — PIP in scan.py ──────────────────────────────► Phase 3 — 8 new seeds
    │                                                                        │
    └──► Phase 2B — pip_system_prompt.py (parallel)                         ▼
                                                                   Phase 4 — fix 2 triggers
                                                                        │
                                                              (all prior phases required)
                                                                        ▼
                                                               Phase 5 — integration test
```

---

## GLOBAL FORBIDDEN LIST — applies to all phases in this sprint

- Do NOT modify `trigger.py` or `trigger_dsl.py` — the dict branch in `_resolve()` already
  handles the merged context without changes.
- Do NOT modify any frontend file.
- Do NOT change the streaming response format or add new API endpoints.
- Do NOT log or persist `personal_note` content to any store or log file.
- Do NOT use `eval()` or execute arbitrary code from the PIP response.
- Do NOT add more than 8 new seeds in Phase 3 — additional seeds are a separate sprint.
- Do NOT mock LLM responses in Phase 5 — the integration test must use the real pipeline.
- Do NOT lower the confidence floor (0.6) on any seed to inflate Phase 5 counts.
- Do NOT hardcode signal values — the PIP must infer them from the actual profile at runtime.
- Do NOT allow the PIP to crash the scan on failure — the fallback must always return `{}`.
- Do NOT rename existing seed IDs — backward compatibility with stored scan results.
- Do NOT skip Phase 1 — the line number from `pip_audit.json` is required by Phase 2A.