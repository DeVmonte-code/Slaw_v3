"""Single-source-of-truth regression for the three MCP servers (Task #26).

The whole point of standing up the MCP servers as thin wrappers is so
that BOTH the in-process verifier (Config A) and the managed-agents
session (Config B) call the SAME Python implementation. If a future
refactor copies a function instead of re-exporting it, the two paths
silently drift — exactly the failure mode this test prevents.

For each registered MCP tool we assert ``tool.impl is <real callable>``
(identity, not equality). Identity is the only check that catches a
shallow copy or a re-decoration.
"""
from __future__ import annotations

from swiss_legal_api import storage
from swiss_legal_api.engine.retrieval import retrieve_for_citation
from swiss_legal_api.mcp_servers import (
    contract_tools,
    swiss_law,
    user_context,
)


def test_swiss_law_tools_resolve_to_canonical_callables() -> None:
    by_name = {t.name: t for t in swiss_law.SERVER.tools}
    # qdrant_search is the thin shape-converter wrapper; what we
    # actually want to pin is that the *underlying* retrieval is the
    # canonical callable. Assert both: the registry tool is the
    # module-level wrapper, and that wrapper closes over the real
    # retrieve_for_citation.
    assert by_name["qdrant_search"].impl is swiss_law.qdrant_search
    assert swiss_law.retrieve_for_citation is retrieve_for_citation
    assert by_name["fetch_article_by_sr"].impl is swiss_law.fetch_article_by_sr
    assert by_name["list_citations"].impl is swiss_law.list_citations


def test_contract_tools_resolve_to_canonical_callables() -> None:
    from swiss_legal_api.engine.scan import run_benefit_scan
    from swiss_legal_api.engine.verify import verify_entitlement

    by_name = {t.name: t for t in contract_tools.SERVER.tools}
    assert by_name["verify_entitlement"].impl is contract_tools.verify_entitlement_tool
    assert by_name["run_benefit_scan"].impl is contract_tools.run_benefit_scan_tool
    # The wrappers must close over the real engine functions, not a
    # local copy. Identity at module scope catches drift.
    assert contract_tools._verify is verify_entitlement
    assert contract_tools._run_scan is run_benefit_scan


def test_user_context_tools_resolve_to_canonical_callables() -> None:
    by_name = {t.name: t for t in user_context.SERVER.tools}
    assert by_name["read_user_docs"].impl is user_context.read_user_docs
    assert by_name["update_user_profile"].impl is user_context.update_user_profile
    # Storage helpers are the durable surface; identity here means a
    # storage migration propagates to the MCP path automatically.
    assert user_context.storage is storage
