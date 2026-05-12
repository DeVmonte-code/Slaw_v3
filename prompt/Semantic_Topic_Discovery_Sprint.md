# Slaw V3: Semantic Topic Discovery Sprint

## What & Why
**What:** Introduce a semantic-first search pathway for the managed agent to discover laws and related topics dynamically, bypassing the current exact-match requirements on SR number and Article. 
**Why:** The current search is strictly citation-driven (`sr_number` + `article` required). To act as an expert legal researcher, the agent needs the ability to formulate broader semantic queries (e.g., "rent reduction due to noise") and retrieve relevant Fedlex articles even when seed citations are exhausted or absent.

## Done looks like
1. The Qdrant engine supports a `retrieve_semantic` method that relies on vector similarity and uses temporal and canton guardrails, but bypasses strict article filtering.
2. The `swiss-law-retrieval-mcp` exposes a new `qdrant_semantic_search` tool to the agent.
3. The managed agent's system prompt explicitly instructs it to extract semantic concepts from user queries and explore edge cases using the new semantic tool.
4. The agent can successfully run and cite articles retrieved from organic semantic searches.

## Out of scope
- Modifying the existing `retrieve_for_citation` method or `qdrant_search` MCP tool (they must remain intact for exact citation verification).
- Changing the Qdrant indexing/seeding scripts (`seed_qdrant.py`).
- Changing the LLM or embedding model configurations.
- Any Frontend changes.

## Done looks like (technical guardrails)
- **Engine Filter:** The `retrieve_semantic` function builds a Qdrant `Filter` utilizing only `.must` conditions for `canton`, `effective_date`, and `repealed_date`. It explicitly omits `FieldCondition(key="sr_number")` and `FieldCondition(key="article")`.
- **MCP Tool Signature:** `@mcp.tool() def qdrant_semantic_search(query: str, canton: str = "CH")`.
- **Agent Constraint:** The system prompt (`SYSTEM_PROMPT` in `bootstrap.py`) strictly enforces that the agent must still rely on the exact authoritative chunks returned for citation, limiting hallucinations.

---

## Steps

### Phase 1: Engine Layer (The Unrestricted Filter)
* **Goal:** Implement semantic retrieval logic without SR/Article keyword constraints.
* **Exact file:** `backend/src/swiss_legal_api/engine/retrieval.py`
* **Code pattern:** 
  - Add a new function `retrieve_semantic(query: str, canton: str = "CH", limit: int = 5, score_threshold: float = 0.6) -> list[RetrievedChunk]`.
  - Create a custom `models.Filter` that enforces `canton` (matching `[canton, "CH"]`) and handles the datetime logic for `effective_date` and `repealed_date`.
  - Embed the query using `embed_query()` and call the Qdrant client's `search()` using the relaxed filter.
* **Validation:** Run unit tests or a fast REPL script to verify `retrieve_semantic("rent reduction", canton="ZH")` returns relevant `RetrievedChunk` instances from various SRs.

### Phase 2: MCP Layer (The New Tool)
* **Goal:** Expose the semantic retrieval as a tool to the managed agents framework.
* **Exact file:** `backend/src/swiss_legal_api/mcp_servers/swiss_law.py`
* **Code pattern:**
  - Import `retrieve_semantic` from `..engine.retrieval`.
  - Add `@mcp.tool() def qdrant_semantic_search(query: str, canton: str = "CH") -> str:`.
  - It should execute `retrieve_semantic`, then format the chunks into a readable JSON or text string containing `sr_number`, `article`, `eli_uri`, and snippet so the agent can inspect context or follow up using `fetch_fedlex_article`.

### Phase 3: Agent Configuration Layer (Prompt Injection)
* **Goal:** Guide the agent to utilize semantic search for organic topic discovery.
* **Exact file:** `backend/src/swiss_legal_api/managed_agents/bootstrap.py`
* **Code pattern:**
  - Update `SYSTEM_PROMPT`. 
  - Add instructions under the Mandate: "When exploring user evidence or looking for related case factors, use `qdrant_semantic_search(query, canton)` to discover applicable legal concepts across the Fedlex corpus. Formulate organic search queries based on the user's situation."
* **Validation:** Run `python -m swiss_legal_api.managed_agents.bootstrap` to propagate the updated prompt and tool configuration to the managed agent endpoint.

---

## Validation
1. Verify syntax and static types: `poetry run mypy backend/src/swiss_legal_api/engine/retrieval.py` (or project equivalent).
2. Start the backend services: `fastapi dev` / `uvicorn`.
3. Submit a test chat/session query referencing a niche topic not explicitly in the base entitlement list. Inspect the console logs to confirm `agent.mcp_tool_use` is invoked for `qdrant_semantic_search` instead of solely `qdrant_search`.

## Relevant files
- `backend/src/swiss_legal_api/engine/retrieval.py`
- `backend/src/swiss_legal_api/mcp_servers/swiss_law.py`
- `backend/src/swiss_legal_api/managed_agents/bootstrap.py`


## Relevant phat folders
- `backend/src/swiss_legal_api/engine/`
- `backend/src/swiss_legal_api/mcp_servers/`
- `backend/src/swiss_legal_api/managed_agents/`
- `backend/src/swiss_legal_api/schemas/`
- `backend/src/swiss_legal_api/models/`