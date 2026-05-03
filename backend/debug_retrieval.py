from datetime import date
from swiss_legal_api.engine.retrieval import _build_query_filter
from swiss_legal_api.schemas.citation import Citation
flt = _build_query_filter(Citation(sr_number="661.11", article="11", paragraph="3", canton="BE", language="de", quote_under_15_words="Das Verfahren ist kostenlos."), "BE", date.today())
from qdrant_client import QdrantClient
from swiss_legal_api.config import settings
client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
hits = client.scroll(
    collection_name=settings.qdrant_collection,
    scroll_filter=flt,
    with_payload=True,
    limit=5
)
print("Records matching filter:", len(hits[0]))
