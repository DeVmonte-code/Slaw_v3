import json
with open('phase3_tmp.md', 'r') as f:
    content = f.read()

json_block = content.split('```json')[1].split('```')[0].strip()

arr_str = f"[{json_block}]"
try:
    arr = json.loads(arr_str)
    print("Parsed JSON successfully.")
except Exception as e:
    print(f"Error parsing JSON: {e}")
    # try to save to debug
    with open('json_debug.json', 'w') as dbg:
        dbg.write(arr_str)

if 'arr' in locals():
    with open('seed/entitlements.json', 'r') as f:
        data = json.load(f)
    data.extend(arr)
    with open('seed/entitlements.json', 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Successfully added {len(arr)} new seeds.")
