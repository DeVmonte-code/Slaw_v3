from __future__ import annotations

from pydantic import BaseModel, Field

from .agent_provenance import AgentProvenance
from .citation import Citation
from .entitlement import EstimatedValue


class EvidenceItem(BaseModel):
    field: str
    value: str | int | float | bool | None


class SupportingDoctrine(BaseModel):
    """Advisory-only doctrinal pointer surfaced alongside a Benefit.

    Sourced from the ``co_curriculum`` Qdrant collection (CO 1-183 +
    specialized PDFs). Never a substitute for the SR + article ``Citation``
    in ``Benefit.citations`` — the citation contract is unchanged. The
    frontend renders these under a "Why this applies" disclosure that is
    visually distinct from the binding-authority "Legal basis" block.
    """

    source_doc: str = Field(
        ...,
        description=(
            "Filename stem of the doctrinal PDF (e.g. 'co_articles_1_183'). "
            "Stable across re-seedings — used as the public identifier."
        ),
    )
    chapter: str | None = Field(
        default=None,
        description=(
            "Optional chapter label from the source document's sidecar "
            "metadata. Falls back to None when the contributor did not "
            "supply a chapter index."
        ),
    )
    section: str | None = Field(
        default=None,
        description=(
            "Optional finer-grained section label inside a chapter "
            "(e.g. '§ 12 — Error of fact'). Sourced from the sidecar's "
            "section_index. Falls back to None when not supplied."
        ),
    )
    score: float = Field(
        ..., ge=0, le=1,
        description="Cosine similarity of the supporting chunk (advisory only).",
    )


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
    # Defaulted to [] so older clients/snapshots and tests that don't yet
    # set the field continue to round-trip unchanged. Empty list is the
    # expected state when the curriculum collection has no PDFs seeded.
    supporting_doctrine: list[SupportingDoctrine] = Field(default_factory=list)
    # Defaulted to None so legacy persisted reports still validate when
    # rehydrated. Newly produced Benefits always carry provenance from
    # the verifier (Task #25); reports written before the audit landed
    # round-trip with a None and surface the "unverified by agent"
    # badge in the UI.
    agent_provenance: AgentProvenance | None = Field(
        default=None,
        description=(
            "Provenance of the Claude call that produced this benefit's "
            "verification. agent_backed=False on every legacy "
            "messages.create call site (Task #26 will flip these)."
        ),
    )
    disclaimer: str = (
        "Not a substitute for advice from a Swiss attorney "
        "registered with a cantonal bar."
    )


class BenefitReport(BaseModel):
    generated_at: str
    profile_hash: str
    benefits: list[Benefit]
    suppressed_count: int = Field(..., ge=0)
    # Entitlements whose every cited article is still backed by the
    # ``__PENDING_FEDLEX_VERBATIM__`` placeholder in seed/law_articles.json.
    # We skip Claude verification for these (the call cannot succeed against
    # the sentinel chunk) and surface the count so dashboards can see how
    # many scans are blocked on the Fedlex backfill follow-up.
    pending_corpus_backfill: int = Field(default=0, ge=0)
