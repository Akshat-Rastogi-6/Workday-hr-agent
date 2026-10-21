"""Step 1 spike: token + one call. Not part of the agent."""
import os, json
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
SAMPLES = ROOT / "samples"
SAMPLES.mkdir(exist_ok=True)

def get_access_token() -> str:
    r = requests.post(
        os.environ["WD_TOKEN_URL"],
        data={"grant_type": "refresh_token", "refresh_token": os.environ["WD_REFRESH_TOKEN"]},
        auth=(os.environ["WD_CLIENT_ID"], os.environ["WD_CLIENT_SECRET"]),
        timeout=30,
    )
    print("token:", r.status_code)
    r.raise_for_status()
    return r.json()["access_token"]

def get(token: str, url: str, **params):
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
    print(f"GET {url} -> {r.status_code}")
    return r

token = get_access_token()

# The common API usually lives next to the URL from View API Clients:
#   .../ccx/api/v1/<tenant>  ->  .../ccx/api/common/v1/<tenant>
rest = os.environ["WD_REST_URL"].rstrip("/")
common = rest.replace("/ccx/api/v1/", "/ccx/api/common/v1/")

for name, url in [("workers", f"{common}/workers"),
                  ("workers_me", f"{common}/workers/me"),
                  ("workers_v1", f"{rest}/workers")]:
    r = get(token, url, limit=5)
    if r.ok:
        body = r.json()
        (SAMPLES / f"{name}.json").write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        print("  top-level keys:", list(body.keys()) if isinstance(body, dict) else type(body))
        print("  total:", body.get("total") if isinstance(body, dict) else "?")
    else:
        print("  ", r.text[:300])