import re
def split_numeric(s):
    if not s: return ()
    return tuple(int(p) if p.isdigit() else p for p in re.split(r'(\d+)', s) if p)

import json
with open("seed/law_articles.fedlex.json") as f:
    data = json.load(f)
keys = [(d["sr_number"], split_numeric(d["article"]), split_numeric(d["paragraph"]), d["language"]) for d in data]
if keys == sorted(keys):
    print("Numeric Sort OK")
else:
    print("Not sorted!")
