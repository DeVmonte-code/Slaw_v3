from swiss_legal_api.ingest.fedlex import FedlexClient
f = FedlexClient()
q = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT DISTINCT ?sr ?title WHERE {
  ?expr jolux:historicalLegalId ?sr .
  ?expr jolux:title ?title .
  FILTER(?sr IN ("661", "661.1", "661.2"))
}
"""
rows = f._sparql(q)
for r in rows:
    print(r.get("sr", {}).get("value"), r.get("title", {}).get("value"))
