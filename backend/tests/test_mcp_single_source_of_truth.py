"""Single-source-of-truth regression for the three MCP servers (Task #26).

The whole point of standing up the MCP servers as thin wrappers is so
that BOTH the in-process verifier (Config A) and the managed-agents
session (Config B) call the SAME Python implementation. If a future
refactor copies a function instead of re-exporting it, the two paths
silently drift — exactly the failure mode this test prevents.

Each MCP tool wrapper is asserted to:

1. Be the actual callable referenced in the server registry
   (``McpServerSpec.tools[].impl is <module>.<wrapper>``), AND
2. Close over the canonical engine-level function as the SAME object
   (``contract_tools._verify is engine.verify.verify_entitlement``).

The second assertion is what catches a "copy-paste analyzer" mistake
where someone re-implements verification logic inside the MCP module
rather than re-exporting the engine function.
"""
from __future__ import annotations

from swiss_legal_api import storage
from swiss_legal_api.engine import retrieval as engine_retrieval
from swiss_legal_api.engine.scan import run_benefit_scan
from swiss_legal_api.engine.sweep import classify_diff
from swiss_legal_api.engine.trigger import evaluate_trigger
from swiss_legal_api.engine.verify import _verify_local, verify_entitlement
from swiss_legal_api.mcp_servers import (
    contract_tools,
    swiss_law,
    user_context,
)

REQUIRED_CONTRACT_TOOLS = frozenset(
    {
        "verify_entitlement",
        "benefit_scan",
        "analyze_tort",
        "evaluate_trigger",
        "classify_diff",
        "score_confidence",
    }
)
REQUIRED_RETRIEVAL_TOOLS = frozenset(
    {"qdrant_search", "fetch_article_by_sr", "list_citations"}
)
REQUIRED_USER_CONTEXT_TOOLS = frozenset(
    {"read_user_docs", "update_user_profile"}
)


def test_swiss_law_tools_resolve_to_canonical_callables() -> None:
    by_name = {t.name: t for t in swiss_law.SERVER.tools}
    # Surface completeness — the agent's bootstrap prompt names these
    # tools by exact string; a rename without a prompt update would
    # silently break the managed path.
    assert frozenset(by_name) == REQUIRED_RETRIEVAL_TOOLS
    # qdrant_search / fetch_article_by_sr / list_citations are the
    # registered impls.
    assert by_name["qdrant_search"].impl is swiss_law.qdrant_search
    assert by_name["fetch_article_by_sr"].impl is swiss_law.fetch_article_by_sr
    assert by_name["list_citations"].impl is swiss_law.list_citations
    # The canonical retrieval function is shared (identity, not equality).
    assert swiss_law.retrieve_for_citation is engine_retrieval.retrieve_for_citation


def test_contract_tools_resolve_to_canonical_callables() -> None:
    by_name = {t.name: t for t in contract_tools.SERVER.tools}
    # The required tool surface for Config B's contract analyzers —
    # changing any of these names is a breaking change vs the agent's
    # system prompt and the audit's MCP-tool-name expectations.
    assert frozenset(by_name) == REQUIRED_CONTRACT_TOOLS
    # Each registered MCP tool is the wrapper module-level function
    # (identity, not equality, so a future copy fails this assertion).
    assert by_name["verify_entitlement"].impl is contract_tools.verify_entitlement_tool
    assert by_name["benefit_scan"].impl is contract_tools.benefit_scan_tool
    assert by_name["analyze_tort"].impl is contract_tools.analyze_tort_tool
    assert by_name["evaluate_trigger"].impl is contract_tools.evaluate_trigger_tool
    assert by_name["classify_diff"].impl is contract_tools.classify_diff_tool
    assert by_name["score_confidence"].impl is contract_tools.score_confidence_tool
    # The wrappers close over the REAL engine functions — no copies,
    # no parallel implementations. This is the single property that
    # guarantees Config A and Config B cannot drift.
    #
    # Critically the contract_tools._verify symbol is bound to
    # ``_verify_local`` (NOT the public ``verify_entitlement``).
    # The public function branches on ``settings.use_managed_agents``
    # and would recurse forever when the flag is on; binding the MCP
    # wrapper to the local helper severs that loop while preserving
    # the single shared implementation.
    assert contract_tools._verify is _verify_local
    assert contract_tools._verify is not verify_entitlement
    assert contract_tools._run_scan is run_benefit_scan
    assert contract_tools._evaluate_trigger is evaluate_trigger
    assert contract_tools._classify_diff is classify_diff


def test_user_context_tools_resolve_to_canonical_callables() -> None:
    by_name = {t.name: t for t in user_context.SERVER.tools}
    assert frozenset(by_name) == REQUIRED_USER_CONTEXT_TOOLS
    assert by_name["read_user_docs"].impl is user_context.read_user_docs
    assert by_name["update_user_profile"].impl is user_context.update_user_profile
    # Storage helpers are the durable surface; identity here means a
    # storage migration propagates to the MCP path automatically.
    assert user_context.storage is storage


def test_score_confidence_applies_translation_only_cap() -> None:
    """The cap value is exported from engine.verify — any change to
    it must propagate to the MCP wrapper without a code edit."""
    from swiss_legal_api.engine.verify import _TRANSLATION_ONLY_CONFIDENCE_CAP

    capped = contract_tools.score_confidence_tool(0.95, translation_only=True)
    assert capped == {"confidence": _TRANSLATION_ONLY_CONFIDENCE_CAP, "capped": True}
    not_capped = contract_tools.score_confidence_tool(0.5, translation_only=True)
    assert not_capped == {"confidence": 0.5, "capped": False}
    auth = contract_tools.score_confidence_tool(0.95, translation_only=False)
    assert auth == {"confidence": 0.95, "capped": False}


def test_bootstrap_vault_payload_includes_env_credentials(
    monkeypatch,
) -> None:
    """Bootstrap registers per-MCP bearer tokens from the environment.

    Without this, every MCP fetch would be unauthenticated — a hard
    requirement of Task #26 vault provisioning.
    """
    from swiss_legal_api.managed_agents import bootstrap

    monkeypatch.setenv("MCP_SWISS_LAW_AUTH_TOKEN", "tok-law")
    monkeypatch.setenv("MCP_CONTRACT_TOOLS_AUTH_TOKEN", "tok-ct")
    monkeypatch.delenv("MCP_USER_CONTEXT_AUTH_TOKEN", raising=False)
    payload = bootstrap._vault_payload()
    creds_by_server = {c["scope"]["mcp_server"]: c for c in payload["credentials"]}
    assert "swiss-law-retrieval-mcp" in creds_by_server
    assert creds_by_server["swiss-law-retrieval-mcp"]["value"] == "tok-law"
    assert "swiss-contract-tools-mcp" in creds_by_server
    # Missing env var → no credential entry (operator opted out).
    assert "swiss-user-context-mcp" not in creds_by_server
    # Safe-for-logging variant must redact the value.
    safe = bootstrap._vault_payload_safe_for_logging()
    safe_by_server = {c["scope"]["mcp_server"]: c for c in safe["credentials"]}
    assert safe_by_server["swiss-law-retrieval-mcp"]["value"] == "***REDACTED***"
