from qdrant_client import QdrantClient
from swiss_legal_api.config import settings
client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
hits = client.scroll(
    collection_name=settings.qdrant_collection,
    scroll_filter={"must": [{"key": "sr_number", "match": {"value": "221.213.1"}}]},
    with_payload=True,
    limit=5
)
print("Records matching 221.213.1:", len(hits[0]))
for h in hits[0]:
    p = h.payload
    print(p)
