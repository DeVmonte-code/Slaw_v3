import os

import pytest

from swiss_legal_api.engine.retrieval import retrieve_for_citation
from swiss_legal_api.schemas import Citation


@pytest.mark.skipif(not os.getenv("QDRANT_URL"), reason="no QDRANT_URL set")
def test_retrieve_known_article():
    cit = Citation(
        sr_number="220", article="270a", language="en",
        quote_under_15_words="The tenant may contest the level.",
    )
    chunks = retrieve_for_citation(cit, "rent reduction")
    assert len(chunks) >= 1
    assert "rent" in chunks[0].text.lower() or "tenant" in chunks[0].text.lower()
