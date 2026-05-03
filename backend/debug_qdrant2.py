from qdrant_client import QdrantClient
from swiss_legal_api.config import settings
client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
hits = client.scroll(
    collection_name=settings.qdrant_collection,
    scroll_filter={
        "must": [
            {"key": "sr_number", "match": {"value": "642.11"}},
            {"key": "article", "match": {"value": "33"}}
        ]
    },
    with_payload=True,
    limit=50
)
print(f"Records matching 642.11 art 33: {len(hits[0])}")
for h in hits[0]:
    print(h.payload)
