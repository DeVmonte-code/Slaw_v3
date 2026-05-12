# Mega-Prompt v3 — Swiss Legal AI Agent "Slaw" (Python Backend + Next.js Frontend, Async Build)

This file contains **two independent Replit Agent prompts** that build the same product asynchronously:

- **PROMPT A — BACKEND** (Python 3.12 + FastAPI + Pydantic v2). Build this **first**, in its own Replit repl. Self-contained; demoable with curl/Swagger without the frontend existing.
- **PROMPT B — FRONTEND** (Next.js 15 + TypeScript + Tailwind). Build this **after** backend phase B10 is green. It consumes the backend's OpenAPI schema to auto-generate its types.

Each prompt has a Mission, Global Rules, Environment Prerequisites, numbered Phases with STOP gates, acceptance criteria, and forbidden lists. The contract between the two projects is:

1. Backend publishes OpenAPI 3.1 at `GET /openapi.json` (FastAPI default)
2. Frontend runs `openapi-typescript` against that URL at build time to generate `types.ts`
3. Shared files `seed/law_articles.json` and `seed/entitlements.json` are copied into both repls verbatim

No runtime dependency between them beyond HTTP. You can ship backend alone, iterate on it, and build the frontend weeks later without breakage.

---

# PROMPT A — BACKEND (Python 3.12 + FastAPI)

Copy everything between `--- BEGIN PROMPT A ---` and `--- END PROMPT A ---` into a fresh Replit repl named `swiss-legal-api`.

--- BEGIN PROMPT A ---

# MISSION

You are building `swiss-legal-api`, the backend for a Proactive Rights Discovery service for Swiss residents. The user does NOT type a legal question. The user submits a structured **ContextProfile** (canton, employment, housing, household, income, life events). The API runs a **Benefit Scan**: (1) evaluates every entry in a curated **EntitlementCatalog** against the profile using a deterministic JSON trigger DSL, (2) for each candidate match, verifies via Claude Messages API grounded in retrieved text from a Qdrant vector store seeded with Swiss federal law articles, (3) ranks and returns a **BenefitReport**. Confidence below the entitlement's floor is suppressed.

The end state of this sprint: running `curl -X POST http://localhost:8000/scan -d @fixtures/luis_profile.json` returns a JSON `BenefitReport` with ≥5 benefits for the seeded Zurich tenant+employee+parent profile, including `rent_reduction_reference_rate` and `childcare_cost_deduction`. Swagger UI at `http://localhost:8000/docs` lets you explore the full API.

Claude is used as a per-entitlement verifier, not as a chat agent. The only chat endpoint (`/chat`) is a benefit-specific follow-up helper, secondary to the main flow.

# GLOBAL RULES (APPLY TO EVERY PHASE)

1. **Language:** Python 3.12 only. No TypeScript or JS in this repl.
2. **Package manager:** `uv` (astral-sh/uv). Fast, deterministic. Not pip, not poetry.
3. **Type safety:** Pydantic v2 (>=2.9) for every schema. `mypy --strict` compatible.
4. **Stop gates:** At the end of each phase there is a `STOP.` line. Print the acceptance output and WAIT for the human to type `continue`. Do not cross phase boundaries autonomously.
5. **Secrets:** Read `ANTHROPIC_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY` from env. On Replit these live in the Secrets pane. Provide `.env.example` for local dev.
6. **No fabricated law:** You must not invent Swiss legal text. Seed entitlements only reference articles whose exact Fedlex-published English text you can reproduce verbatim. If an article cannot be reproduced faithfully, drop the entitlement that depends on it and note it in `README.md`.
7. **No web fetches at runtime:** The scan engine calls only the Anthropic API and Qdrant. No scraping, no requests to Fedlex at request time.
8. **Ask before deviating:** If an instruction conflicts with a real Replit constraint, stop and ask.
9. **No Git commits by the Agent:** Create files only.

# ENVIRONMENT PREREQUISITES (SET BEFORE STARTING)

- Replit Secrets: `ANTHROPIC_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`
- Qdrant Cloud free-tier cluster created, reachable, empty
- `uv` installable via `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`

If anything is missing, stop and list what is missing.

---

## PHASE B0 — BOOTSTRAP

**Files to create:**
- `/.python-version`
- `/pyproject.toml`
- `/.env.example`
- `/.gitignore`
- `/README.md`
- `/ruff.toml`

**Exact content for `.python-version`:**
```
3.12
```

**Exact content for `pyproject.toml`:**
```toml
[project]
name = "swiss-legal-api"
version = "0.1.0"
description = "Proactive Rights Discovery API for Swiss residents"
requires-python = ">=3.12,<3.13"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.32.0",
  "pydantic>=2.9.0",
  "pydantic-settings>=2.6.0",
  "anthropic>=0.39.0",
  "qdrant-client>=1.12.0",
  "sentence-transformers>=3.2.0",
  "httpx>=0.27.0",
  "python-dotenv>=1.0.1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3.0",
  "pytest-asyncio>=0.24.0",
  "respx>=0.21.1",
  "ruff>=0.7.0",
  "mypy>=1.13.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]

[tool.mypy]
strict = true
python_version = "3.12"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/swiss_legal_api"]
```

**Exact content for `.env.example`:**
```
ANTHROPIC_API_KEY=sk-ant-...
QDRANT_URL=https://xxxx.cloud.qdrant.io
QDRANT_API_KEY=...
CLAUDE_MODEL=claude-sonnet-4-6
QDRANT_COLLECTION=swiss_law
EMBEDDING_MODEL=intfloat/multilingual-e5-small
SCAN_CONCURRENCY=3
```

**Exact content for `ruff.toml`:**
```toml
line-length = 100
target-version = "py312"

[lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]
```

**Exact content for `.gitignore`:**
```
.venv
__pycache__
*.pyc
.env
.pytest_cache
.mypy_cache
.ruff_cache
dist
build
*.egg-info
openapi.json
```

**Commands:**
```
uv --version
uv python install 3.12
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
python --version
python -c "import fastapi, pydantic, anthropic, qdrant_client; print('ok')"
```

**Acceptance criteria:**
- `uv` version prints
- Python version prints 3.12.x
- Import check prints `ok`
- Directory contains exactly the six files above

**Forbidden:**
- Do not create `src/` or `tests/` yet
- Do not add any dependency not listed above
- Do not touch FastAPI code yet

STOP. Print `Phase B0 complete.` and wait for `continue`.

---

## PHASE B1 — PYDANTIC SCHEMAS

**Files to create:**
- `/src/swiss_legal_api/__init__.py`
- `/src/swiss_legal_api/schemas/__init__.py`
- `/src/swiss_legal_api/schemas/citation.py`
- `/src/swiss_legal_api/schemas/context_profile.py`
- `/src/swiss_legal_api/schemas/trigger_dsl.py`
- `/src/swiss_legal_api/schemas/entitlement.py`
- `/src/swiss_legal_api/schemas/benefit_report.py`
- `/tests/__init__.py`
- `/tests/test_schemas.py`

**Exact content for `schemas/citation.py`:**
```python
from __future__ import annotations
import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator

SR_RE = re.compile(r"^\d+(\.\d+)?$")


class Citation(BaseModel):
    sr_number: str = Field(..., description="Fedlex SR number like '220'")
    article: str = Field(..., min_length=1)
    paragraph: str | None = None
    canton: str = Field(default="CH")
    language: Literal["de", "fr", "it", "en"]
    quote_under_15_words: str

    @field_validator("sr_number")
    @classmethod
    def _sr(cls, v: str) -> str:
        if not SR_RE.match(v):
            raise ValueError("sr_number must match ^\\d+(\\.\\d+)?$")
        return v

    @field_validator("quote_under_15_words")
    @classmethod
    def _quote(cls, v: str) -> str:
        if len(v.strip().split()) > 15:
            raise ValueError("quote must be 15 words or fewer")
        return v
```

**Exact content for `schemas/context_profile.py`:**
```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

Canton = Literal[
    "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR", "JU", "LU",
    "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG", "TI", "UR", "VD", "VS", "ZG", "ZH",
]
Language = Literal["de", "fr", "it", "en"]
EmploymentStatus = Literal[
    "employee_full_time", "employee_part_time", "self_employed",
    "business_owner", "unemployed", "student", "retired",
]
HousingStatus = Literal["tenant", "owner", "living_with_family"]
MaritalStatus = Literal["single", "married", "registered_partnership", "divorced", "widowed"]
IncomeBand = Literal["lt_30k", "30_50k", "50_80k", "80_120k", "120_200k", "gt_200k"]
BusinessActivity = Literal["none", "freelance", "sole_proprietor", "gmbh", "ag"]
LifeEventKind = Literal[
    "moved_canton", "had_child", "got_married", "got_divorced",
    "lost_job", "started_business", "started_studies", "bought_property", "retired",
]


class LifeEvent(BaseModel):
    event: LifeEventKind
    year: int
    month: int | None = Field(default=None, ge=1, le=12)


class ContextProfile(BaseModel):
    canton: Canton
    language: Language = "de"

    employment_status: EmploymentStatus
    employer_sector: str | None = None
    employment_start_year: int | None = None
    weekly_hours: float | None = Field(default=None, ge=0, le=80)

    housing_status: HousingStatus
    rental_start_year: int | None = None
    lease_reference_rate_tracked: bool | None = None
    rent_chf_monthly: float | None = Field(default=None, ge=0)

    household_size: int = Field(default=1, ge=1, le=12)
    children_count: int = Field(default=0, ge=0, le=10)
    children_ages: list[int] = Field(default_factory=list)
    marital_status: MaritalStatus

    income_band_chf: IncomeBand
    has_third_pillar: bool = False
    third_pillar_chf_this_year: float | None = Field(default=None, ge=0)

    business_activity: BusinessActivity = "none"
    rd_spend_chf_this_year: float | None = Field(default=None, ge=0)

    commute_km_daily: float | None = Field(default=None, ge=0)
    childcare_cost_chf_yearly: float | None = Field(default=None, ge=0)

    recent_life_events: list[LifeEvent] = Field(default_factory=list)
    free_text_narrative: str | None = Field(default=None, max_length=2000)
```

**Exact content for `schemas/trigger_dsl.py`:**
```python
from __future__ import annotations
from typing import Annotated, Any
from pydantic import BaseModel, Field, RootModel


class All(BaseModel):
    all: list[TriggerExpr]


class Any_(BaseModel):
    any: list[TriggerExpr]


class Not(BaseModel):
    not_: TriggerExpr = Field(alias="not")

    model_config = {"populate_by_name": True}


class Eq(BaseModel):
    eq: tuple[str, str | int | float | bool]


class Gte(BaseModel):
    gte: tuple[str, float]


class Lte(BaseModel):
    lte: tuple[str, float]


class Gt(BaseModel):
    gt: tuple[str, float]


class Lt(BaseModel):
    lt: tuple[str, float]


class In(BaseModel):
    in_: tuple[str, list[str | int | float]] = Field(alias="in")

    model_config = {"populate_by_name": True}


class Between(BaseModel):
    between: tuple[str, tuple[float, float]]


class Exists(BaseModel):
    exists: str


class EventWithinYears(BaseModel):
    event_within_years: tuple[str, int]


TriggerExpr = (
    All | Any_ | Not | Eq | Gte | Lte | Gt | Lt | In | Between | Exists | EventWithinYears
)

All.model_rebuild()
Any_.model_rebuild()
Not.model_rebuild()
```

**Exact content for `schemas/entitlement.py`:**
```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field
from .citation import Citation
from .trigger_dsl import TriggerExpr


class TitleI18n(BaseModel):
    de: str
    fr: str | None = None
    it: str | None = None
    en: str


Category = Literal[
    "tax_deduction", "tenancy_right", "employment_right", "family_benefit",
    "business_subsidy", "social_security", "consumer_protection",
]
RequiredAction = Literal[
    "claim_letter_to_landlord", "tax_declaration_field", "employer_request",
    "cantonal_application", "federal_application", "consultation_with_lawyer",
]
ValuePer = Literal["year", "one_time", "month"]


class EstimatedValue(BaseModel):
    min: float = Field(..., ge=0)
    max: float = Field(..., ge=0)
    per: ValuePer = "year"


class Entitlement(BaseModel):
    id: str = Field(..., min_length=1)
    title: TitleI18n
    category: Category
    jurisdiction: str = Field(..., min_length=2)
    source_citations: list[Citation] = Field(..., min_length=1)
    trigger: TriggerExpr
    estimated_value_chf: EstimatedValue
    required_action: RequiredAction
    action_template_id: str | None = None
    time_limit_days: int | None = None
    confidence_floor: float = Field(default=0.6, ge=0, le=1)
```

**Exact content for `schemas/benefit_report.py`:**
```python
from __future__ import annotations
from pydantic import BaseModel, Field
from .citation import Citation
from .entitlement import EstimatedValue


class EvidenceItem(BaseModel):
    field: str
    value: str | int | float | bool | None


class Benefit(BaseModel):
    entitlement_id: str
    title: str
    category: str
    estimated_value_chf: EstimatedValue
    confidence: float = Field(..., ge=0, le=1)
    citations: list[Citation] = Field(..., min_length=1)
    evidence: list[EvidenceItem]
    required_action: str
    action_template_id: str | None = None
    time_limit_days: int | None = None
    llm_reasoning: str
    disclaimer: str = (
        "Not a substitute for advice from a Swiss attorney "
        "registered with a cantonal bar."
    )


class BenefitReport(BaseModel):
    generated_at: str
    profile_hash: str
    benefits: list[Benefit]
    suppressed_count: int = Field(..., ge=0)
```

**Exact content for `schemas/__init__.py`:**
```python
from .citation import Citation
from .context_profile import ContextProfile, LifeEvent
from .entitlement import Entitlement, EstimatedValue, TitleI18n
from .benefit_report import Benefit, BenefitReport, EvidenceItem
from .trigger_dsl import TriggerExpr

__all__ = [
    "Citation", "ContextProfile", "LifeEvent",
    "Entitlement", "EstimatedValue", "TitleI18n",
    "Benefit", "BenefitReport", "EvidenceItem",
    "TriggerExpr",
]
```

**Exact content for `tests/test_schemas.py`:**
```python
from swiss_legal_api.schemas import (
    Citation, ContextProfile, Entitlement, Benefit,
)
import pytest


def test_citation_accepts_valid():
    c = Citation(
        sr_number="220", article="24", paragraph="1",
        language="en", quote_under_15_words="Fundamental error allows rescission under specified conditions.",
    )
    assert c.canton == "CH"


def test_citation_rejects_long_quote():
    with pytest.raises(ValueError):
        Citation(
            sr_number="220", article="24",
            language="en",
            quote_under_15_words="a b c d e f g h i j k l m n o p q",
        )


def test_context_profile_minimal():
    p = ContextProfile(
        canton="ZH",
        employment_status="employee_full_time",
        housing_status="tenant",
        marital_status="married",
        income_band_chf="80_120k",
    )
    assert p.language == "de"
    assert p.children_count == 0


def test_entitlement_parses():
    e = Entitlement.model_validate({
        "id": "rent_reduction_reference_rate",
        "title": {"de": "Mietzinsreduktion", "en": "Rent reduction"},
        "category": "tenancy_right",
        "jurisdiction": "CH",
        "source_citations": [{
            "sr_number": "220", "article": "270a", "language": "en",
            "quote_under_15_words": "The tenant may contest the level of the rent.",
        }],
        "trigger": {"all": [{"eq": ["housing_status", "tenant"]}]},
        "estimated_value_chf": {"min": 500, "max": 3000, "per": "year"},
        "required_action": "claim_letter_to_landlord",
    })
    assert e.confidence_floor == 0.6


def test_benefit_requires_citation():
    with pytest.raises(ValueError):
        Benefit(
            entitlement_id="x", title="x", category="tax_deduction",
            estimated_value_chf={"min": 0, "max": 0, "per": "year"},
            confidence=0.7, citations=[], evidence=[],
            required_action="tax_declaration_field", llm_reasoning="...",
        )
```

**Commands:**
```
uv pip install -e ".[dev]"
pytest tests/test_schemas.py -v
ruff check src tests
mypy src
```

**Acceptance criteria:**
- 5/5 tests pass
- `ruff check` clean
- `mypy` clean

**Forbidden:**
- Do not implement the scan engine yet
- Do not import anthropic or qdrant_client in these files

STOP. Print `Phase B1 complete.` Wait for `continue`.

---

## PHASE B2 — SEED CORPUS (law_articles.json + entitlements.json)

**Files to create:**
- `/seed/law_articles.json`
- `/seed/entitlements.json`
- `/tests/test_seed.py`

**`seed/law_articles.json`:** JSON array of at least 20 objects with shape:
```json
{
  "sr_number": "220",
  "article": "270a",
  "paragraph": "1",
  "language": "en",
  "text": "The tenant may contest the level of the rent..."
}
```

Include these articles using verbatim Fedlex English translations. If you cannot reproduce an article's text faithfully from training, exclude it and note in `README.md` which ones you dropped:

- CO (SR 220): 257e, 270a, 321c, 328, 335c, 41, 42, 43, 62, 63, 24, 28, 1, 18
- DBG (SR 642.11): 9, 26, 33, 33a
- BVG (SR 831.40): 82
- AVIG (SR 837.0): 8, 9

**`seed/entitlements.json`:** JSON array of exactly 15 `Entitlement` objects. Each references citations whose `sr_number`+`article` appear in `law_articles.json`. Required IDs with their trigger JSON:

| id | trigger | source |
|---|---|---|
| `rent_reduction_reference_rate` | `{"all":[{"eq":["housing_status","tenant"]},{"lte":["rental_start_year",2022]},{"eq":["lease_reference_rate_tracked",true]}]}` | CO 270a |
| `rent_deposit_interest` | `{"all":[{"eq":["housing_status","tenant"]},{"gte":["rent_chf_monthly",1]}]}` | CO 257e |
| `employer_health_protection` | `{"all":[{"in":["employment_status",["employee_full_time","employee_part_time"]]},{"gte":["weekly_hours",35]}]}` | CO 328 |
| `overtime_compensation` | `{"all":[{"in":["employment_status",["employee_full_time","employee_part_time"]]}]}` | CO 321c |
| `notice_period_seniority` | `{"all":[{"in":["employment_status",["employee_full_time","employee_part_time"]]},{"lte":["employment_start_year",2020]}]}` | CO 335c |
| `childcare_cost_deduction` | `{"all":[{"gte":["children_count",1]},{"gte":["childcare_cost_chf_yearly",1]}]}` | DBG 33 |
| `commuting_cost_deduction` | `{"all":[{"in":["employment_status",["employee_full_time","employee_part_time","self_employed"]]},{"gte":["commute_km_daily",1]}]}` | DBG 26 |
| `professional_training_deduction` | `{"all":[{"in":["employment_status",["employee_full_time","employee_part_time","self_employed"]]}]}` | DBG 33a |
| `third_pillar_deduction` | `{"all":[{"eq":["has_third_pillar",true]},{"gte":["third_pillar_chf_this_year",1]}]}` | BVG 82 |
| `marriage_taxation_neutralization` | `{"eq":["marital_status","married"]}` | DBG 9 |
| `unemployment_insurance_entitlement` | `{"all":[{"eq":["employment_status","unemployed"]}]}` | AVIG 8 |
| `moving_canton_tax_adjustment` | `{"event_within_years":["moved_canton",2]}` | DBG 9 |
| `fundamental_error_rescission` | `{"all":[]}` (INFO-only, floor 0.5) | OR 24 |
| `rd_business_deduction_hint` | `{"all":[{"in":["business_activity",["freelance","sole_proprietor","gmbh","ag"]]},{"gte":["rd_spend_chf_this_year",1]}]}` | DBG 26 |
| `tort_claim_placeholder` | `{"all":[]}` (INFO-only, floor 0.5) | CO 41 |

Fill in `title.de`, `title.en`, `estimated_value_chf`, `required_action`, `time_limit_days` with realistic values.

**Exact content for `tests/test_seed.py`:**
```python
import json
from pathlib import Path
from swiss_legal_api.schemas import Entitlement, Citation


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_law_articles_parse():
    data = json.loads((_root() / "seed" / "law_articles.json").read_text())
    assert isinstance(data, list) and len(data) >= 20
    for row in data:
        assert {"sr_number", "article", "language", "text"} <= row.keys()


def test_entitlements_parse_and_count():
    data = json.loads((_root() / "seed" / "entitlements.json").read_text())
    assert len(data) == 15
    ids = set()
    for row in data:
        e = Entitlement.model_validate(row)
        ids.add(e.id)
    assert "rent_reduction_reference_rate" in ids
    assert "childcare_cost_deduction" in ids


def test_entitlement_citations_exist_in_corpus():
    articles = json.loads((_root() / "seed" / "law_articles.json").read_text())
    available = {(a["sr_number"], a["article"]) for a in articles}
    entitlements = json.loads((_root() / "seed" / "entitlements.json").read_text())
    for row in entitlements:
        for cit in row["source_citations"]:
            assert (cit["sr_number"], cit["article"]) in available, (
                f"Entitlement {row['id']} cites missing article "
                f"SR {cit['sr_number']} Art. {cit['article']}"
            )
```

**Commands:**
```
pytest tests/test_seed.py -v
```

**Acceptance criteria:**
- 3/3 seed tests pass
- `seed/law_articles.json` has ≥20 rows
- `seed/entitlements.json` has exactly 15 rows
- Every entitlement's citation resolves to an article present in the corpus

**Forbidden:**
- Do not invent legal text
- Do not add cantonal statutes
- Do not exceed 30 articles or 15 entitlements

STOP. Print `Phase B2 complete.` Wait for `continue`.

---

## PHASE B3 — QDRANT SEEDER

**Files to create:**
- `/src/swiss_legal_api/config.py`
- `/src/swiss_legal_api/seeding/__init__.py`
- `/src/swiss_legal_api/seeding/embedder.py`
- `/src/swiss_legal_api/seeding/seed_qdrant.py`

**Exact content for `config.py`:**
```python
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "swiss_law"
    embedding_model: str = "intfloat/multilingual-e5-small"
    scan_concurrency: int = 3


settings = Settings()
```

**Exact content for `seeding/embedder.py`:**
```python
from __future__ import annotations
from functools import lru_cache
from sentence_transformers import SentenceTransformer

from ..config import settings


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model)


def embed_passage(text: str) -> list[float]:
    model = get_embedder()
    vec = model.encode(f"passage: {text}", normalize_embeddings=True)
    return vec.tolist()


def embed_query(text: str) -> list[float]:
    model = get_embedder()
    vec = model.encode(f"query: {text}", normalize_embeddings=True)
    return vec.tolist()
```

**Exact content for `seeding/seed_qdrant.py`:**
```python
from __future__ import annotations
import json
import sys
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from ..config import settings
from .embedder import embed_passage


def main() -> int:
    if not settings.qdrant_url or not settings.qdrant_api_key:
        print("QDRANT_URL and QDRANT_API_KEY required", file=sys.stderr)
        return 1

    seed = Path(__file__).resolve().parents[3] / "seed" / "law_articles.json"
    articles = json.loads(seed.read_text())

    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

    existing = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(size=384, distance=qmodels.Distance.COSINE),
        )

    for field in ("sr_number", "article", "language"):
        try:
            client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field,
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass

    points: list[qmodels.PointStruct] = []
    for i, a in enumerate(articles, start=1):
        vec = embed_passage(a["text"])
        points.append(qmodels.PointStruct(id=i, vector=vec, payload=a))

    client.upsert(
        collection_name=settings.qdrant_collection,
        points=points,
        wait=True,
    )
    print(f"Seeded {len(points)} articles into {settings.qdrant_collection}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Commands:**
```
python -m swiss_legal_api.seeding.seed_qdrant
```

**Acceptance criteria:**
- Script exits 0
- Prints `Seeded N articles into swiss_law` where N ≥ 20
- Qdrant dashboard shows the collection with N points

**Forbidden:**
- Do not crawl Fedlex
- Do not change the embedding model without asking
- Do not seed more than the law_articles.json content

STOP. Print the seeder output and `Phase B3 complete.` Wait for `continue`.

---

## PHASE B4 — TRIGGER EVALUATOR (pure Python, no I/O)

**Files to create:**
- `/src/swiss_legal_api/engine/__init__.py`
- `/src/swiss_legal_api/engine/trigger.py`
- `/tests/test_trigger.py`

**Exact content for `engine/trigger.py`:**
```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..schemas import ContextProfile
from ..schemas.trigger_dsl import (
    All, Any_, Not, Eq, Gte, Lte, Gt, Lt, In, Between,
    Exists, EventWithinYears, TriggerExpr,
)


@dataclass
class EvalResult:
    matched: bool
    evidence: list[dict[str, Any]] = field(default_factory=list)


def _resolve(profile: ContextProfile, path: str) -> Any:
    obj: Any = profile
    for key in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif hasattr(obj, key):
            obj = getattr(obj, key)
        else:
            return None
        if obj is None:
            return None
    return obj


def _record(path: str, profile: ContextProfile) -> dict[str, Any]:
    v = _resolve(profile, path)
    if isinstance(v, (str, int, float, bool)) or v is None:
        return {"field": path, "value": v}
    return {"field": path, "value": str(v)}


def evaluate_trigger(expr: TriggerExpr, profile: ContextProfile) -> EvalResult:
    if isinstance(expr, All):
        subs = [evaluate_trigger(e, profile) for e in expr.all]
        return EvalResult(
            matched=all(s.matched for s in subs),
            evidence=[e for s in subs for e in s.evidence],
        )
    if isinstance(expr, Any_):
        subs = [evaluate_trigger(e, profile) for e in expr.any]
        return EvalResult(
            matched=any(s.matched for s in subs),
            evidence=[e for s in subs for e in s.evidence],
        )
    if isinstance(expr, Not):
        r = evaluate_trigger(expr.not_, profile)
        return EvalResult(matched=not r.matched, evidence=r.evidence)
    if isinstance(expr, Eq):
        f, val = expr.eq
        ev = _record(f, profile)
        return EvalResult(matched=ev["value"] == val, evidence=[ev])
    if isinstance(expr, Gte):
        f, val = expr.gte
        ev = _record(f, profile)
        x = ev["value"]
        return EvalResult(matched=isinstance(x, (int, float)) and x >= val, evidence=[ev])
    if isinstance(expr, Lte):
        f, val = expr.lte
        ev = _record(f, profile)
        x = ev["value"]
        return EvalResult(matched=isinstance(x, (int, float)) and x <= val, evidence=[ev])
    if isinstance(expr, Gt):
        f, val = expr.gt
        ev = _record(f, profile)
        x = ev["value"]
        return EvalResult(matched=isinstance(x, (int, float)) and x > val, evidence=[ev])
    if isinstance(expr, Lt):
        f, val = expr.lt
        ev = _record(f, profile)
        x = ev["value"]
        return EvalResult(matched=isinstance(x, (int, float)) and x < val, evidence=[ev])
    if isinstance(expr, In):
        f, vals = expr.in_
        ev = _record(f, profile)
        return EvalResult(matched=ev["value"] in vals, evidence=[ev])
    if isinstance(expr, Between):
        f, (lo, hi) = expr.between
        ev = _record(f, profile)
        x = ev["value"]
        return EvalResult(
            matched=isinstance(x, (int, float)) and lo <= x <= hi, evidence=[ev]
        )
    if isinstance(expr, Exists):
        ev = _record(expr.exists, profile)
        return EvalResult(matched=ev["value"] is not None, evidence=[ev])
    if isinstance(expr, EventWithinYears):
        name, years = expr.event_within_years
        threshold = datetime.now().year - years
        matches = [e for e in profile.recent_life_events if e.event == name and e.year >= threshold]
        ev = {"field": f"recent_life_events[{name}]", "value": len(matches)}
        return EvalResult(matched=len(matches) > 0, evidence=[ev])
    return EvalResult(matched=False)
```

**Exact content for `tests/test_trigger.py`:**
```python
import pytest
from swiss_legal_api.schemas import ContextProfile
from swiss_legal_api.schemas.trigger_dsl import (
    All, Eq, Gte, Lte, In,
)
from swiss_legal_api.engine.trigger import evaluate_trigger


@pytest.fixture
def luis() -> ContextProfile:
    return ContextProfile.model_validate({
        "canton": "ZH",
        "employment_status": "employee_full_time",
        "employment_start_year": 2018,
        "weekly_hours": 42,
        "housing_status": "tenant",
        "rental_start_year": 2018,
        "lease_reference_rate_tracked": True,
        "rent_chf_monthly": 2400,
        "household_size": 4,
        "children_count": 2,
        "children_ages": [3, 6],
        "marital_status": "married",
        "income_band_chf": "120_200k",
        "has_third_pillar": True,
        "third_pillar_chf_this_year": 7056,
        "commute_km_daily": 12,
        "childcare_cost_chf_yearly": 18000,
    })


def test_rent_reduction_trigger_matches(luis: ContextProfile):
    expr = All.model_validate({"all": [
        {"eq": ["housing_status", "tenant"]},
        {"lte": ["rental_start_year", 2022]},
        {"eq": ["lease_reference_rate_tracked", True]},
    ]})
    r = evaluate_trigger(expr, luis)
    assert r.matched is True
    assert len(r.evidence) == 3


def test_childcare_trigger_matches(luis: ContextProfile):
    expr = All.model_validate({"all": [
        {"gte": ["children_count", 1]},
        {"gte": ["childcare_cost_chf_yearly", 1]},
    ]})
    assert evaluate_trigger(expr, luis).matched is True


def test_unemployment_trigger_false_for_employed(luis: ContextProfile):
    expr = Eq.model_validate({"eq": ["employment_status", "unemployed"]})
    assert evaluate_trigger(expr, luis).matched is False


def test_in_trigger(luis: ContextProfile):
    expr = In.model_validate({"in": ["employment_status", ["employee_full_time", "self_employed"]]})
    assert evaluate_trigger(expr, luis).matched is True
```

**Commands:**
```
pytest tests/test_trigger.py -v
mypy src
ruff check src tests
```

**Acceptance criteria:**
- 4/4 trigger tests pass
- mypy + ruff clean

**Forbidden:**
- Do not make network calls in this module
- Do not import anthropic, qdrant_client here

STOP. Print `Phase B4 complete.` Wait for `continue`.

---

## PHASE B5 — RETRIEVAL SERVICE

**Files to create:**
- `/src/swiss_legal_api/engine/retrieval.py`
- `/tests/test_retrieval.py`

**Exact content for `engine/retrieval.py`:**
```python
from __future__ import annotations
from dataclasses import dataclass
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from ..config import settings
from ..schemas import Citation
from ..seeding.embedder import embed_query


@dataclass
class RetrievedChunk:
    text: str
    score: float


def _client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def retrieve_for_citation(citation: Citation, extra_query: str) -> list[RetrievedChunk]:
    vec = embed_query(f"{citation.article} {extra_query}")
    client = _client()
    results = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=vec,
        limit=3,
        query_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="sr_number", match=qmodels.MatchValue(value=citation.sr_number),
                ),
                qmodels.FieldCondition(
                    key="article", match=qmodels.MatchValue(value=citation.article),
                ),
            ]
        ),
        with_payload=True,
    )
    return [RetrievedChunk(text=r.payload.get("text", ""), score=r.score) for r in results]
```

**Exact content for `tests/test_retrieval.py`:**
```python
import os
import pytest
from swiss_legal_api.schemas import Citation
from swiss_legal_api.engine.retrieval import retrieve_for_citation


@pytest.mark.skipif(not os.getenv("QDRANT_URL"), reason="no QDRANT_URL set")
def test_retrieve_known_article():
    cit = Citation(
        sr_number="220", article="270a", language="en",
        quote_under_15_words="The tenant may contest the level.",
    )
    chunks = retrieve_for_citation(cit, "rent reduction")
    assert len(chunks) >= 1
    assert "rent" in chunks[0].text.lower() or "tenant" in chunks[0].text.lower()
```

**Commands:**
```
pytest tests/test_retrieval.py -v
```

**Acceptance criteria:**
- Test passes when QDRANT_URL is set (skip is acceptable only if env absent)

**Forbidden:**
- Do not add filters beyond sr_number + article
- Do not call Claude here

STOP. Print `Phase B5 complete.` Wait for `continue`.

---

## PHASE B6 — VERIFICATION SERVICE

**Files to create:**
- `/src/swiss_legal_api/engine/verify.py`

**Exact content for `engine/verify.py`:**
```python
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from anthropic import AsyncAnthropic

from ..config import settings
from ..schemas import Citation, ContextProfile, Entitlement
from .retrieval import retrieve_for_citation

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

SYSTEM = """You verify whether a specific Swiss legal article supports a specific claimed entitlement for a specific user context.

Rules:
- Output ONLY valid JSON of shape {"supports": bool, "confidence": number 0..1, "reasoning": string, "best_quote": string (<= 15 words)}.
- Use the retrieved article text as the authoritative source.
- If the article does not support the entitlement for this user context, set supports=false and explain why.
- Do not hallucinate article text. If the retrieved text does not clearly support the claim, prefer supports=false.
- confidence reflects strength of textual support, not absolute legal certainty."""


@dataclass
class VerifyResult:
    supports: bool
    confidence: float
    reasoning: str
    best_citation: Citation


async def verify_entitlement(
    entitlement: Entitlement,
    profile: ContextProfile,
    triggered_evidence: list[dict],
) -> VerifyResult:
    cit = entitlement.source_citations[0]
    chunks = retrieve_for_citation(cit, entitlement.title.en)
    retrieved_text = "\n\n".join(
        f"[{i+1}] score={c.score:.3f}: {c.text}" for i, c in enumerate(chunks)
    ) or "NO RESULTS — treat supports as false"

    safe_fields = {
        "canton": profile.canton,
        "employment_status": profile.employment_status,
        "housing_status": profile.housing_status,
        "household_size": profile.household_size,
        "children_count": profile.children_count,
        "marital_status": profile.marital_status,
        "income_band_chf": profile.income_band_chf,
        "business_activity": profile.business_activity,
    }

    user_content = f"""Entitlement: {entitlement.title.en}
Claim: This user is entitled to this under SR {cit.sr_number} Art. {cit.article}.
Category: {entitlement.category}
Jurisdiction: {entitlement.jurisdiction}

User profile (structured fields only):
{json.dumps(safe_fields, indent=2)}

Triggering evidence:
{json.dumps(triggered_evidence, indent=2)}

Retrieved legal text:
{retrieved_text}

Respond with JSON only."""

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=settings.claude_model,
        max_tokens=600,
        system=SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    m = _JSON_RE.search(text)
    raw = m.group(0) if m else text
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return VerifyResult(
            supports=False, confidence=0.0,
            reasoning="LLM output was not valid JSON",
            best_citation=cit,
        )

    quote = " ".join(str(parsed.get("best_quote", "")).strip().split()[:14])
    return VerifyResult(
        supports=bool(parsed.get("supports", False)),
        confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0.0)))),
        reasoning=str(parsed.get("reasoning", "")),
        best_citation=cit.model_copy(update={"quote_under_15_words": quote or cit.quote_under_15_words}),
    )
```

**Commands:**
```
mypy src
ruff check src
```

**Acceptance criteria:**
- mypy + ruff clean
- No tests here yet — integration happens in B7

**Forbidden:**
- Do not call this module from within a FastAPI request handler yet

STOP. Print `Phase B6 complete.` Wait for `continue`.

---

## PHASE B7 — SCAN ORCHESTRATOR

**Files to create:**
- `/src/swiss_legal_api/engine/scan.py`
- `/src/swiss_legal_api/catalog.py`
- `/tests/test_scan.py`
- `/fixtures/luis_profile.json`

**Exact content for `catalog.py`:**
```python
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
from .schemas import Entitlement


@lru_cache(maxsize=1)
def load_catalog() -> list[Entitlement]:
    path = Path(__file__).resolve().parents[2] / "seed" / "entitlements.json"
    data = json.loads(path.read_text())
    return [Entitlement.model_validate(row) for row in data]
```

**Exact content for `engine/scan.py`:**
```python
from __future__ import annotations
import asyncio
import hashlib
import json
import math
from datetime import datetime

from ..config import settings
from ..schemas import Benefit, BenefitReport, ContextProfile, Entitlement, EvidenceItem
from .trigger import evaluate_trigger
from .verify import verify_entitlement


async def _verify_one(
    e: Entitlement, profile: ContextProfile, evidence: list[dict],
    sem: asyncio.Semaphore,
) -> tuple[Entitlement, list[dict], object | None]:
    async with sem:
        try:
            v = await verify_entitlement(e, profile, evidence)
            return e, evidence, v
        except Exception:
            return e, evidence, None


async def run_benefit_scan(
    profile: ContextProfile, catalog: list[Entitlement]
) -> BenefitReport:
    triggered = []
    for e in catalog:
        r = evaluate_trigger(e.trigger, profile)
        if r.matched:
            triggered.append((e, r.evidence))

    sem = asyncio.Semaphore(settings.scan_concurrency)
    results = await asyncio.gather(*[_verify_one(e, profile, ev, sem) for e, ev in triggered])

    benefits: list[Benefit] = []
    suppressed = 0
    for e, evidence, v in results:
        if v is None or not v.supports or v.confidence < e.confidence_floor:
            suppressed += 1
            continue
        title = getattr(e.title, profile.language, None) or e.title.en
        benefits.append(Benefit(
            entitlement_id=e.id,
            title=title,
            category=e.category,
            estimated_value_chf=e.estimated_value_chf,
            confidence=v.confidence,
            citations=[v.best_citation, *e.source_citations[1:]],
            evidence=[EvidenceItem(**ev) for ev in evidence],
            required_action=e.required_action,
            action_template_id=e.action_template_id,
            time_limit_days=e.time_limit_days,
            llm_reasoning=v.reasoning,
        ))

    benefits.sort(
        key=lambda b: b.confidence * math.log1p(b.estimated_value_chf.max),
        reverse=True,
    )

    profile_hash = hashlib.sha256(
        json.dumps(profile.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()[:16]

    return BenefitReport(
        generated_at=datetime.utcnow().isoformat() + "Z",
        profile_hash=profile_hash,
        benefits=benefits,
        suppressed_count=suppressed,
    )
```

**Exact content for `fixtures/luis_profile.json`:**
```json
{
  "canton": "ZH",
  "language": "de",
  "employment_status": "employee_full_time",
  "employment_start_year": 2018,
  "weekly_hours": 42,
  "housing_status": "tenant",
  "rental_start_year": 2018,
  "lease_reference_rate_tracked": true,
  "rent_chf_monthly": 2400,
  "household_size": 4,
  "children_count": 2,
  "children_ages": [3, 6],
  "marital_status": "married",
  "income_band_chf": "120_200k",
  "has_third_pillar": true,
  "third_pillar_chf_this_year": 7056,
  "business_activity": "none",
  "commute_km_daily": 12,
  "childcare_cost_chf_yearly": 18000,
  "recent_life_events": []
}
```

**Exact content for `tests/test_scan.py`:**
```python
import json
import os
import pytest
from pathlib import Path
from swiss_legal_api.schemas import ContextProfile
from swiss_legal_api.catalog import load_catalog
from swiss_legal_api.engine.scan import run_benefit_scan


pytestmark = pytest.mark.skipif(
    not (os.getenv("ANTHROPIC_API_KEY") and os.getenv("QDRANT_URL")),
    reason="requires ANTHROPIC_API_KEY and QDRANT_URL",
)


async def test_luis_profile_returns_required_benefits():
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "luis_profile.json"
    profile = ContextProfile.model_validate(json.loads(fixture.read_text()))
    report = await run_benefit_scan(profile, load_catalog())
    assert len(report.benefits) >= 5
    ids = {b.entitlement_id for b in report.benefits}
    assert "rent_reduction_reference_rate" in ids
    assert "childcare_cost_deduction" in ids
```

**Commands:**
```
pytest tests/test_scan.py -v
```

**Acceptance criteria:**
- Test passes: ≥5 benefits, includes both required IDs

**Forbidden:**
- Do not add streaming yet
- Do not parallelize beyond semaphore=3

STOP. Print `Phase B7 complete.` Wait for `continue`.

---

## PHASE B8 — FASTAPI APP

**Files to create:**
- `/src/swiss_legal_api/api/__init__.py`
- `/src/swiss_legal_api/api/main.py`
- `/src/swiss_legal_api/api/chat.py`
- `/tests/test_api.py`

**Exact content for `api/main.py`:**
```python
from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..catalog import load_catalog
from ..engine.scan import run_benefit_scan
from ..schemas import BenefitReport, ContextProfile
from .chat import answer_follow_up

app = FastAPI(
    title="Swiss Legal Agent API",
    version="0.1.0",
    description="Proactive Rights Discovery for Swiss residents.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    benefit_id: str | None = None


class ChatResponse(BaseModel):
    answer: str


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/scan", response_model=BenefitReport)
async def scan(profile: ContextProfile) -> BenefitReport:
    try:
        return await run_benefit_scan(profile, load_catalog())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    try:
        answer = await answer_follow_up(req.message, req.benefit_id)
        return ChatResponse(answer=answer)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
```

**Exact content for `api/chat.py`:**
```python
from __future__ import annotations
from anthropic import AsyncAnthropic

from ..catalog import load_catalog
from ..config import settings
from ..engine.retrieval import retrieve_for_citation


async def answer_follow_up(message: str, benefit_id: str | None) -> str:
    context = ""
    if benefit_id:
        ent = next((e for e in load_catalog() if e.id == benefit_id), None)
        if ent:
            chunks = retrieve_for_citation(ent.source_citations[0], ent.title.en)
            context = (
                f"Entitlement: {ent.title.en}\n\n"
                f"Relevant article text:\n"
                + "\n\n".join(c.text for c in chunks)
            )

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=settings.claude_model,
        max_tokens=800,
        system=(
            "You answer follow-up questions about a specific Swiss legal entitlement. "
            "Cite SR number and article. Keep quotes under 15 words. Remind the user "
            "you are not a Swiss attorney."
        ),
        messages=[{"role": "user", "content": f"{context}\n\nUser question: {message}"}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")
```

**Exact content for `tests/test_api.py`:**
```python
import json
import os
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport
from swiss_legal_api.api.main import app


async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health")
        assert r.status_code == 200
        assert r.json() == {"ok": True}


async def test_openapi_schema_available():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert "paths" in schema
        assert "/scan" in schema["paths"]
        assert "/chat" in schema["paths"]


@pytest.mark.skipif(
    not (os.getenv("ANTHROPIC_API_KEY") and os.getenv("QDRANT_URL")),
    reason="requires live secrets",
)
async def test_scan_endpoint_live():
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "luis_profile.json"
    payload = json.loads(fixture.read_text())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t", timeout=180) as c:
        r = await c.post("/scan", json=payload)
        assert r.status_code == 200
        report = r.json()
        assert len(report["benefits"]) >= 5
        ids = {b["entitlement_id"] for b in report["benefits"]}
        assert "rent_reduction_reference_rate" in ids
        assert "childcare_cost_deduction" in ids
```

**Commands:**
```
pytest tests/test_api.py -v
uvicorn swiss_legal_api.api.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
sleep 3
curl -s http://localhost:8000/health
curl -s http://localhost:8000/openapi.json | python -c "import sys, json; d=json.load(sys.stdin); print('paths:', list(d['paths'].keys()))"
kill $SERVER_PID
```

**Acceptance criteria:**
- Health + openapi tests pass (2/2 offline)
- Live scan test passes if secrets set
- `curl /health` returns `{"ok":true}`
- `curl /openapi.json` returns JSON with `/scan` and `/chat` listed

**Forbidden:**
- Do not add authentication
- Do not add streaming endpoints
- Do not add any endpoint beyond `/health`, `/scan`, `/chat`, and the FastAPI-default `/openapi.json` + `/docs`

STOP. Print `Phase B8 complete.` Wait for `continue`.

---

## PHASE B9 — OPENAPI EXPORT SCRIPT

**Files to create:**
- `/scripts/export_openapi.py`

**Exact content:**
```python
"""Dump the OpenAPI schema to openapi.json at repo root.

The frontend repo consumes this file via openapi-typescript to generate its
TypeScript types. Run this script whenever the API surface changes.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from swiss_legal_api.api.main import app


def main() -> int:
    schema = app.openapi()
    out = Path(__file__).resolve().parents[1] / "openapi.json"
    out.write_text(json.dumps(schema, indent=2))
    print(f"Wrote {out} with {len(schema.get('paths', {}))} paths")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Commands:**
```
python scripts/export_openapi.py
test -f openapi.json && echo "openapi.json exists" && python -c "import json; d=json.load(open('openapi.json')); print('paths:', list(d['paths'].keys()))"
```

**Acceptance criteria:**
- Script exits 0
- `openapi.json` exists at repo root
- File lists `/scan` and `/chat` in paths

**Forbidden:**
- Do not commit `openapi.json` — it's generated (already in .gitignore)

STOP. Print `Phase B9 complete.` Wait for `continue`.

---

## PHASE B10 — END-TO-END BACKEND SMOKE

**Files to create:**
- `/scripts/smoke.sh`

**Exact content:**
```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Lint + types ==="
ruff check src tests
mypy src

echo "=== Unit tests (offline) ==="
pytest tests/test_schemas.py tests/test_seed.py tests/test_trigger.py -v

echo "=== Start API ==="
uvicorn swiss_legal_api.api.main:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
trap "kill $SERVER_PID 2>/dev/null || true" EXIT
sleep 4

echo "=== Health ==="
curl -sf http://localhost:8000/health

echo "=== OpenAPI paths ==="
curl -sf http://localhost:8000/openapi.json | python -c "import sys, json; d=json.load(sys.stdin); print(list(d['paths'].keys()))"

echo "=== Live scan (Luis profile) ==="
RESP=$(curl -sf -X POST http://localhost:8000/scan \
  -H "content-type: application/json" \
  -d @fixtures/luis_profile.json \
  --max-time 180)

COUNT=$(echo "$RESP" | python -c "import sys, json; print(len(json.load(sys.stdin)['benefits']))")
echo "Benefits returned: $COUNT"
if [ "$COUNT" -lt 5 ]; then
  echo "FAIL: expected >= 5 benefits, got $COUNT"
  exit 1
fi

echo "$RESP" | python -c "
import sys, json
ids = [b['entitlement_id'] for b in json.load(sys.stdin)['benefits']]
assert 'rent_reduction_reference_rate' in ids, 'rent_reduction missing'
assert 'childcare_cost_deduction' in ids, 'childcare_cost_deduction missing'
print('required IDs present')
"

echo "=== Export OpenAPI ==="
python scripts/export_openapi.py

echo "=== Backend smoke PASSED ==="
```

**Commands:**
```
chmod +x scripts/smoke.sh
./scripts/smoke.sh
```

**Acceptance criteria:**
- Script exits 0
- Output ends with `=== Backend smoke PASSED ===`
- `openapi.json` is written at repo root, ready for frontend consumption

STOP. Print `Phase B10 complete. Backend v1 sprint done. Ready for frontend build.` Do not start frontend work.

---

# DEFERRED (DO NOT TOUCH IN THIS SPRINT)

- Cantonal statute ingestion (ZH LS, BE BSG, GE RS)
- Fedlex SPARQL auto-ingestion + nightly diff
- User document upload
- Authentication / multi-tenancy
- Letter template engine
- Langfuse observability, RAGAS evals
- Streaming SSE
- Prompt caching
- Swiss-hosted deployment
- The six contract-analysis tools (analyze_contract, identify_phase, diagnose_problems, assess_performance, analyze_tort, analyze_unjust_enrichment)

--- END PROMPT A ---

---
---

# PROMPT B — FRONTEND (Next.js 15 + TypeScript)

Copy everything between `--- BEGIN PROMPT B ---` and `--- END PROMPT B ---` into a fresh Replit repl named `swiss-legal-web`. **Run this AFTER the backend phase B10 smoke test passes.** The backend must be running and reachable.

--- BEGIN PROMPT B ---

# MISSION

You are building `swiss-legal-web`, the frontend for a Proactive Rights Discovery service. The backend (a separate Python FastAPI service at `http://localhost:8000`, already shipped) owns all business logic, the scan engine, Qdrant retrieval, and Claude calls. The frontend is pure presentation: (1) a profile wizard form at `/` that collects a `ContextProfile`, (2) a results page at `/results` that renders ranked benefit cards from `/scan`, (3) a per-benefit follow-up chat drawer that calls `/chat`.

The frontend has NO business logic. Types come from the backend's OpenAPI schema, regenerated at every build via `openapi-typescript`. The end state: running `pnpm dev` and filling the form with the Luis-profile defaults, submitting, and seeing at least 5 benefit cards render with citations, confidence, evidence, and required action — matching the backend's live `/scan` response.

# GLOBAL RULES

1. **Language:** TypeScript only. pnpm-managed Next.js 15 App Router.
2. **Types:** Auto-generated from backend's `/openapi.json` via `openapi-typescript`. Do not hand-write request/response schemas. If a type doesn't exist in the generated file, add it to the backend and regenerate; do not redefine.
3. **Stop gates:** Every phase ends with `STOP.` — wait for `continue`.
4. **Secrets:** `NEXT_PUBLIC_API_URL` only. No Anthropic or Qdrant keys belong here.
5. **Ask before deviating:** if a backend endpoint shape is not what you expect, stop and tell the human — do not "fix" by shimming it on the frontend.
6. **No Git commits by the Agent.**

# ENVIRONMENT PREREQUISITES (BEFORE STARTING)

- Backend is running at `BACKEND_URL` (default `http://localhost:8000`)
- `curl -sf $BACKEND_URL/health` returns `{"ok":true}`
- `curl -sf $BACKEND_URL/openapi.json | head -c 200` returns valid JSON
- Node 20+ and pnpm available

If any of these fail, STOP and tell the human the backend is not reachable. Do not proceed.

---

## PHASE F0 — BOOTSTRAP NEXT.JS 15

**Files to create:**
- `/package.json`
- `/tsconfig.json`
- `/next.config.mjs`
- `/tailwind.config.ts`
- `/postcss.config.mjs`
- `/.env.example`
- `/.env.local`
- `/.gitignore`
- `/app/layout.tsx`
- `/app/globals.css`
- `/app/page.tsx` (placeholder "hello")

**Exact content for `package.json`:**
```json
{
  "name": "swiss-legal-web",
  "version": "0.1.0",
  "private": true,
  "packageManager": "pnpm@9.15.0",
  "engines": { "node": ">=20" },
  "scripts": {
    "dev": "next dev -p 3000",
    "build": "next build",
    "start": "next start -p 3000",
    "lint": "next lint",
    "types:api": "openapi-typescript ${NEXT_PUBLIC_API_URL:-http://localhost:8000}/openapi.json -o lib/api-types.ts"
  },
  "dependencies": {
    "next": "15.0.3",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "openapi-fetch": "^0.13.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "autoprefixer": "^10.4.20",
    "eslint": "^8.57.0",
    "eslint-config-next": "15.0.3",
    "openapi-typescript": "^7.4.0",
    "postcss": "^8.4.47",
    "tailwindcss": "^3.4.14",
    "typescript": "^5.6.0"
  }
}
```

**Exact content for `tsconfig.json`:**
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "es2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "baseUrl": ".",
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
```

**Exact content for `next.config.mjs`:**
```js
/** @type {import('next').NextConfig} */
export default {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
};
```

**Exact content for `tailwind.config.ts`:**
```ts
import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
} satisfies Config;
```

**Exact content for `postcss.config.mjs`:**
```js
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
```

**Exact content for `.env.example`:**
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Exact content for `.env.local`:**
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Exact content for `.gitignore`:**
```
node_modules
.next
out
dist
.env.local
*.log
```

**Exact content for `app/globals.css`:**
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body { background: #fafafa; color: #111; }
```

**Exact content for `app/layout.tsx`:**
```tsx
import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Swiss Legal Rights Scan",
  description: "Discover rights, deductions, and protections under Swiss law.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans antialiased">{children}</body>
    </html>
  );
}
```

**Exact content for `app/page.tsx` (placeholder):**
```tsx
export default function Home() {
  return <main className="p-8">Bootstrap ok — profile form added in F3</main>;
}
```

**Commands:**
```
pnpm install
pnpm build
pnpm dev &
SERVER_PID=$!
sleep 5
curl -sf http://localhost:3000 | head -c 200
kill $SERVER_PID
```

**Acceptance criteria:**
- `pnpm build` exits 0
- `curl http://localhost:3000` returns HTML containing `Bootstrap ok`

**Forbidden:**
- Do not add any UI library (shadcn, MUI, etc.) — plain Tailwind only
- Do not scaffold pages other than `/` and the layout
- Do not call the backend yet

STOP. Print `Phase F0 complete.` Wait for `continue`.

---

## PHASE F1 — GENERATE TYPES FROM BACKEND OPENAPI

**Files to create:**
- `/lib/api-types.ts` (generated, committed-to-disk)

**Commands:**
```
pnpm run types:api
test -f lib/api-types.ts && wc -l lib/api-types.ts
grep -c "ContextProfile" lib/api-types.ts
grep -c "BenefitReport" lib/api-types.ts
```

**Acceptance criteria:**
- `lib/api-types.ts` exists and has >100 lines
- Both `ContextProfile` and `BenefitReport` string matches > 0 (types are referenced)
- File compiles when imported — verify with `pnpm build`

**Forbidden:**
- Do not edit `lib/api-types.ts` by hand
- Do not add any other type files — everything comes from the generated one

STOP. Print `Phase F1 complete.` Wait for `continue`.

---

## PHASE F2 — API CLIENT

**Files to create:**
- `/lib/api-client.ts`

**Exact content:**
```ts
import createClient from "openapi-fetch";
import type { paths } from "./api-types";

const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = createClient<paths>({ baseUrl });

// Convenience re-exports of the concrete schemas the frontend uses
export type ContextProfile =
  paths["/scan"]["post"]["requestBody"]["content"]["application/json"];
export type BenefitReport =
  paths["/scan"]["post"]["responses"]["200"]["content"]["application/json"];
export type Benefit = BenefitReport["benefits"][number];
export type Citation = Benefit["citations"][number];
```

**Commands:**
```
pnpm build
```

**Acceptance criteria:**
- Build exits 0
- No TS errors on the generated type imports

**Forbidden:**
- Do not write a custom fetch wrapper — use `openapi-fetch`
- Do not hardcode URLs other than the baseUrl from env

STOP. Print `Phase F2 complete.` Wait for `continue`.

---

## PHASE F3 — PROFILE WIZARD (`/`)

**Replace** `/app/page.tsx` with the wizard form.

**Exact content:**
```tsx
"use client";
import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, type ContextProfile } from "@/lib/api-client";

const CANTONS = ["AG","BE","BL","BS","FR","GE","GR","LU","SG","SO","TI","VD","VS","ZG","ZH"];

export default function Home() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(evt: FormEvent<HTMLFormElement>) {
    evt.preventDefault();
    setLoading(true); setError(null);
    const fd = new FormData(evt.currentTarget);
    const profile: ContextProfile = {
      canton: fd.get("canton") as ContextProfile["canton"],
      language: "de",
      employment_status: fd.get("employment_status") as ContextProfile["employment_status"],
      employment_start_year: numOrUndef(fd, "employment_start_year"),
      weekly_hours: numOrUndef(fd, "weekly_hours"),
      housing_status: fd.get("housing_status") as ContextProfile["housing_status"],
      rental_start_year: numOrUndef(fd, "rental_start_year"),
      lease_reference_rate_tracked: fd.get("lease_reference_rate_tracked") === "on",
      rent_chf_monthly: numOrUndef(fd, "rent_chf_monthly"),
      household_size: Number(fd.get("household_size")) || 1,
      children_count: Number(fd.get("children_count")) || 0,
      children_ages: [],
      marital_status: fd.get("marital_status") as ContextProfile["marital_status"],
      income_band_chf: fd.get("income_band_chf") as ContextProfile["income_band_chf"],
      has_third_pillar: fd.get("has_third_pillar") === "on",
      third_pillar_chf_this_year: numOrUndef(fd, "third_pillar_chf_this_year"),
      business_activity: "none",
      commute_km_daily: numOrUndef(fd, "commute_km_daily"),
      childcare_cost_chf_yearly: numOrUndef(fd, "childcare_cost_chf_yearly"),
      recent_life_events: [],
    };

    const { data, error: err } = await api.POST("/scan", { body: profile });
    setLoading(false);
    if (err || !data) { setError(String(err ?? "unknown error")); return; }
    sessionStorage.setItem("benefit_report", JSON.stringify(data));
    router.push("/results");
  }

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="mb-2 text-3xl font-bold">Swiss Legal Rights Scan</h1>
      <p className="mb-6 text-gray-600">
        Tell us your context. We will check Swiss federal law and tell you which rights,
        deductions, and subsidies you may be entitled to and are not currently claiming.
      </p>
      <form onSubmit={onSubmit} className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Select name="canton" label="Canton" defaultValue="ZH" options={CANTONS} />
        <Select name="employment_status" label="Employment" defaultValue="employee_full_time"
          options={["employee_full_time","employee_part_time","self_employed","unemployed","retired","student"]} />
        <Num name="employment_start_year" label="Employment start year" defaultValue={2018} />
        <Num name="weekly_hours" label="Weekly hours" defaultValue={42} />
        <Select name="housing_status" label="Housing" defaultValue="tenant"
          options={["tenant","owner","living_with_family"]} />
        <Num name="rental_start_year" label="Rental start year" defaultValue={2018} />
        <Check name="lease_reference_rate_tracked" label="Lease tracks reference rate" defaultChecked />
        <Num name="rent_chf_monthly" label="Monthly rent (CHF)" defaultValue={2400} />
        <Num name="household_size" label="Household size" defaultValue={4} />
        <Num name="children_count" label="Children" defaultValue={2} />
        <Select name="marital_status" label="Marital status" defaultValue="married"
          options={["single","married","registered_partnership","divorced","widowed"]} />
        <Select name="income_band_chf" label="Income band" defaultValue="120_200k"
          options={["lt_30k","30_50k","50_80k","80_120k","120_200k","gt_200k"]} />
        <Check name="has_third_pillar" label="Has 3rd pillar" defaultChecked />
        <Num name="third_pillar_chf_this_year" label="3rd pillar this year (CHF)" defaultValue={7056} />
        <Num name="commute_km_daily" label="Daily commute (km)" defaultValue={12} />
        <Num name="childcare_cost_chf_yearly" label="Childcare yearly (CHF)" defaultValue={18000} />
        <button type="submit" disabled={loading}
          className="md:col-span-2 rounded bg-emerald-600 px-4 py-2 text-white disabled:opacity-50">
          {loading ? "Scanning..." : "Run Rights Scan"}
        </button>
        {error && <p className="md:col-span-2 text-red-600">{error}</p>}
      </form>
    </main>
  );
}

function numOrUndef(fd: FormData, key: string): number | undefined {
  const v = fd.get(key); if (v == null || v === "") return undefined;
  const n = Number(v); return Number.isFinite(n) ? n : undefined;
}
function Select({ name, label, defaultValue, options }:
  { name: string; label: string; defaultValue: string; options: readonly string[] }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span>{label}</span>
      <select name={name} defaultValue={defaultValue} className="rounded border px-2 py-1">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  );
}
function Num({ name, label, defaultValue }: { name: string; label: string; defaultValue: number }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span>{label}</span>
      <input name={name} type="number" defaultValue={defaultValue} className="rounded border px-2 py-1" />
    </label>
  );
}
function Check({ name, label, defaultChecked }: { name: string; label: string; defaultChecked?: boolean }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input name={name} type="checkbox" defaultChecked={defaultChecked} /> {label}
    </label>
  );
}
```

**Commands:**
```
pnpm build
```

**Acceptance criteria:**
- Build exits 0
- Starting `pnpm dev` shows the form with all fields populated to Luis defaults

**Forbidden:**
- Do not validate on the frontend — backend returns 422 for bad input and the user sees the error
- Do not add any multi-step wizard — single form

STOP. Print `Phase F3 complete.` Wait for `continue`.

---

## PHASE F4 — RESULTS PAGE (`/results`)

**Files to create:**
- `/app/results/page.tsx`

**Exact content:**
```tsx
"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import type { BenefitReport } from "@/lib/api-client";
import { BenefitCard } from "@/components/BenefitCard";

export default function Results() {
  const [report, setReport] = useState<BenefitReport | null>(null);
  useEffect(() => {
    const raw = sessionStorage.getItem("benefit_report");
    if (raw) setReport(JSON.parse(raw) as BenefitReport);
  }, []);

  if (!report) {
    return (
      <main className="mx-auto max-w-3xl p-8">
        <p className="text-gray-600">No report. <Link href="/" className="text-emerald-700 underline">Run a scan</Link>.</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl p-8">
      <Link href="/" className="text-sm text-emerald-700 underline">&larr; new scan</Link>
      <h1 className="mt-2 mb-4 text-3xl font-bold">
        Your potential rights ({report.benefits.length})
      </h1>
      <p className="mb-6 text-sm text-gray-500">
        Suppressed low-confidence matches: {report.suppressed_count}
      </p>
      <div className="flex flex-col gap-4">
        {report.benefits.map((b) => <BenefitCard key={b.entitlement_id} benefit={b} />)}
      </div>
    </main>
  );
}
```

**Files to create:**
- `/components/BenefitCard.tsx`

**Exact content:**
```tsx
"use client";
import type { Benefit } from "@/lib/api-client";

export function BenefitCard({ benefit: b }: { benefit: Benefit }) {
  const cits = b.citations.map((c) => `SR ${c.sr_number} Art. ${c.article}`).join("; ");
  return (
    <article className="rounded-lg border bg-white p-4 shadow-sm">
      <header className="flex items-start justify-between gap-4">
        <h2 className="text-xl font-semibold">{b.title}</h2>
        <span className="rounded bg-emerald-100 px-2 py-0.5 text-sm text-emerald-800">
          {(b.confidence * 100).toFixed(0)}%
        </span>
      </header>
      <p className="mt-1 text-sm text-gray-600">
        {b.category.replace(/_/g, " ")} · est. CHF {b.estimated_value_chf.min}–{b.estimated_value_chf.max} / {b.estimated_value_chf.per}
      </p>
      <dl className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="font-medium">Citations</dt>
          <dd>{cits}</dd>
        </div>
        <div>
          <dt className="font-medium">Required action</dt>
          <dd>
            {b.required_action.replace(/_/g, " ")}
            {b.time_limit_days ? ` (within ${b.time_limit_days} days)` : ""}
          </dd>
        </div>
      </dl>
      <div className="mt-3 text-sm">
        <p className="font-medium">Why this matched</p>
        <ul className="list-disc pl-5 text-gray-700">
          {b.evidence.map((e, i) => (
            <li key={i}>{e.field} = {String(e.value)}</li>
          ))}
        </ul>
      </div>
      <p className="mt-3 text-sm"><span className="font-medium">Reasoning:</span> {b.llm_reasoning}</p>
      <p className="mt-3 text-xs text-gray-500">{b.disclaimer}</p>
    </article>
  );
}
```

**Commands:**
```
pnpm build
```

**Acceptance criteria:**
- Build exits 0

**Forbidden:**
- Do not add CSV export, printing, or other features yet
- Do not touch animations or transitions

STOP. Print `Phase F4 complete.` Wait for `continue`.

---

## PHASE F5 — FOLLOW-UP CHAT ON BENEFIT CARDS

**Files to create:**
- `/components/AskFollowUp.tsx`

**Exact content:**
```tsx
"use client";
import { useState } from "react";
import { api } from "@/lib/api-client";

export function AskFollowUp({ benefitId }: { benefitId: string }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [a, setA] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function ask() {
    setLoading(true); setA(null);
    const { data, error } = await api.POST("/chat", {
      body: { message: q, benefit_id: benefitId },
    });
    setLoading(false);
    setA(error ? String(error) : (data?.answer ?? ""));
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="mt-3 text-sm text-emerald-700 underline">
        Ask a follow-up question
      </button>
    );
  }

  return (
    <div className="mt-3 rounded border bg-gray-50 p-3">
      <textarea value={q} onChange={(e) => setQ(e.target.value)}
        rows={3} placeholder="Ask about this specific entitlement…"
        className="w-full rounded border px-2 py-1 text-sm" />
      <div className="mt-2 flex items-center gap-2">
        <button onClick={ask} disabled={loading || !q}
          className="rounded bg-emerald-600 px-3 py-1 text-sm text-white disabled:opacity-50">
          {loading ? "Thinking…" : "Ask"}
        </button>
        <button onClick={() => setOpen(false)} className="text-sm text-gray-600">close</button>
      </div>
      {a && <pre className="mt-3 whitespace-pre-wrap text-sm">{a}</pre>}
    </div>
  );
}
```

**Update** `/components/BenefitCard.tsx` to include `<AskFollowUp benefitId={b.entitlement_id} />` at the bottom.

**Commands:**
```
pnpm build
```

**Acceptance criteria:**
- Build exits 0
- Clicking "Ask a follow-up" on a card reveals the textarea and POSTs to `/chat`

**Forbidden:**
- Do not add chat history persistence
- Do not add streaming yet

STOP. Print `Phase F5 complete.` Wait for `continue`.

---

## PHASE F6 — ENV / DOCKER / DEPLOY PREP

**Files to create:**
- `/Dockerfile`
- `/.dockerignore`

**Exact content for `Dockerfile`:**
```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
RUN corepack enable && pnpm install --frozen-lockfile || pnpm install

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN corepack enable && pnpm build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
EXPOSE 3000
CMD ["node_modules/.bin/next", "start", "-p", "3000"]
```

**Exact content for `.dockerignore`:**
```
node_modules
.next
.git
.env.local
```

**Commands:**
```
docker build --build-arg NEXT_PUBLIC_API_URL=http://host.docker.internal:8000 -t swiss-legal-web:dev . || echo "Docker build optional on Replit"
```

**Acceptance criteria:**
- Dockerfile and dockerignore present
- Docker build is optional on Replit (Replit may not have docker installed); the file is just prepared for production

**Forbidden:**
- Do not deploy yet

STOP. Print `Phase F6 complete.` Wait for `continue`.

---

## PHASE F7 — END-TO-END FRONTEND SMOKE

**Files to create:**
- `/scripts/smoke.sh`

**Exact content:**
```bash
#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8000}"

echo "=== Verify backend reachable ==="
curl -sf "$BACKEND_URL/health"
curl -sf "$BACKEND_URL/openapi.json" | head -c 100 && echo

echo "=== Regenerate types ==="
pnpm run types:api

echo "=== Build ==="
pnpm build

echo "=== Start ==="
pnpm start &
WEB_PID=$!
trap "kill $WEB_PID 2>/dev/null || true" EXIT
sleep 6

echo "=== Check root page renders form ==="
HTML=$(curl -sf http://localhost:3000)
echo "$HTML" | grep -q "Swiss Legal Rights Scan" && echo "PASS: title present"
echo "$HTML" | grep -q "Run Rights Scan" && echo "PASS: submit button present"

echo "=== Frontend smoke PASSED ==="
```

**Commands:**
```
chmod +x scripts/smoke.sh
./scripts/smoke.sh
```

**Acceptance criteria:**
- Script exits 0
- Output ends with `=== Frontend smoke PASSED ===`

STOP. Print `Phase F7 complete. Frontend v1 sprint done.` Do not start any other work.

---

# DEFERRED (DO NOT TOUCH IN THIS SPRINT)

- Authentication (Clerk / Auth.js)
- Server Actions for form submission (stay on client-side fetch for now)
- Internationalization (i18n) — UI is English only in v1
- PDF export of BenefitReport
- Chat history persistence across benefits
- Streaming SSE consumption
- Playwright E2E tests
- Multi-language toggle (`language` field is hardcoded to `de` in the profile for v1)

--- END PROMPT B ---

---
---

# BUILD ORDER & OPERATIONAL NOTES

1. Create the `swiss-legal-api` Replit repl. Set the three backend secrets. Paste PROMPT A. Run phases B0→B10, typing `continue` between each.
2. After B10 prints `Backend v1 sprint done`, leave the backend running (`uvicorn` on port 8000). Note the Replit-provided public URL.
3. Create the `swiss-legal-web` Replit repl. Set `NEXT_PUBLIC_API_URL` to the backend's public URL (or use port forwarding for `http://localhost:8000` if same machine). Paste PROMPT B. Run phases F0→F7.
4. Type changes in the backend (adding a field to `ContextProfile`, a new endpoint) propagate to the frontend by re-running `pnpm run types:api` in the frontend repl. TypeScript errors will tell you exactly what needs updating in the UI.
5. The two repls never import from each other. Their only contract is the OpenAPI schema and the shared seed files (`seed/law_articles.json`, `seed/entitlements.json`), which you copy verbatim into whichever repl needs them.

If backend B10 passes but frontend F1 fails with "Cannot reach /openapi.json", the backend is not reachable from the frontend repl — check the `NEXT_PUBLIC_API_URL` env var and CORS settings on the backend (already permissive via `CORSMiddleware(allow_origins=["*"])`).
