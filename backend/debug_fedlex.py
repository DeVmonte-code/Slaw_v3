from swiss_legal_api.ingest.fedlex import FedlexClient
client = FedlexClient()
meta = client.fetch_act_metadata("642.11")
print("act_uri:", meta.act_uri)
print("effective:", meta.effective_date)
print("repealed:", meta.repealed_date)
