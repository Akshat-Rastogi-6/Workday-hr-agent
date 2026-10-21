"""Print the shape of each sample, and only the fields relevant to the mapping."""
import json
from pathlib import Path

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
INTERESTING = ("id", "employee", "manager", "location", "hire", "balance", "plan",
               "quantity", "unit", "total", "descriptor", "title", "type", "superior")
HIDE = ("birth", "phone", "address", "email", "href")

def walk(obj, path="", depth=0, max_depth=4):
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if any(h in k.lower() for h in HIDE):
                continue
            if isinstance(v, (dict, list)):
                walk(v, p, depth + 1, max_depth)
            elif any(w in k.lower() for w in INTERESTING):
                print(f"    {p} = {str(v)[:70]}")
    elif isinstance(obj, list):
        print(f"    {path}  [list, {len(obj)} items]")
        for i, item in enumerate(obj[:3]):
            walk(item, f"{path}[{i}]", depth + 1, max_depth)

for f in sorted(SAMPLES.glob("*.json")):
    name = f.stem
    data = json.loads(f.read_text(encoding="utf-8"))
    keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
    print(f"\n=== {name}   top-level: {keys}")
    walk(data)