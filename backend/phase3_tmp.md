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

