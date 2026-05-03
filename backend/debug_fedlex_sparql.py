query = """
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
SELECT ?act ?eif ?nolonger ?expr ?lang WHERE {
  ?expr jolux:historicalLegalId "642.11" .
  ?expr jolux:language ?lang .
  ?act jolux:isRealizedBy ?expr .
  OPTIONAL { ?act jolux:dateEntryInForce ?eif }
  OPTIONAL { ?act jolux:dateNoLongerInForce ?nolonger }
}
"""
import httpx
resp = httpx.post("https://fedlex.data.admin.ch/sparqlendpoint", data={"query": query}, headers={"Accept": "application/sparql-results+json"})
for r in resp.json()["results"]["bindings"]:
    print({k: v.get("value") for k, v in r.items()})
