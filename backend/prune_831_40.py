import json
import glob

paths = ["seed/law_articles.json"]
paths.extend(glob.glob("tests/fixtures/*.json"))

for path in paths:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if isinstance(data, list):
            filtered = [d for d in data if d.get("sr_number") != "831.40"]
            if len(filtered) < len(data):
                print(f"Removed {len(data) - len(filtered)} records from {path}")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(filtered, f, ensure_ascii=False, indent=2)
                    f.write("\n")
    except Exception as e:
        # Ignore errors for files that aren't lists of dicts
        pass
