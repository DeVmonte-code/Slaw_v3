import json
with open("seed/law_articles.fedlex.json") as f:
    data = json.load(f)
keys = [(d["sr_number"], d["article"], d["paragraph"], d["language"]) for d in data]
if keys == sorted(keys):
    print("Sorted OK")
else:
    print("Not sorted!")
