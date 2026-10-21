"""Does the compensation RaaS work with our bearer token, and how is it prompted?"""
import os, json
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

r = requests.post(
    os.environ["WD_TOKEN_URL"],
    data={"grant_type": "refresh_token", "refresh_token": os.environ["WD_REFRESH_TOKEN"]},
    auth=(os.environ["WD_CLIENT_ID"], os.environ["WD_CLIENT_SECRET"]),
    timeout=30,
)
r.raise_for_status()
H = {"Authorization": f"Bearer {r.json()['access_token']}"}
URL = os.environ["WD_RAAS_COMP_URL"]

def run(label, **params):
    resp = requests.get(URL, headers=H, params={"format": "json", **params}, timeout=60)
    print(f"\n{resp.status_code}  {label}")
    if not resp.ok:
        print("   ", resp.text[:300])
        return
    rows = resp.json().get("Report_Entry", [])
    print(f"    rows: {len(rows)}")
    if rows:
        print("    keys:", list(rows[0].keys()))
        print("    first:", json.dumps(rows[0], ensure_ascii=False))

run("no prompt (expect ALL workers if the prompt isn't wired)")
run("prompt by Employee_ID", **{"Worker!Employee_ID": "21142"})
run("prompt by WID",         **{"Worker!WID": "693618e08cc11000cb2fc27ed9ca0001"})
run("no prompt (should now be an error or 0 rows, not everyone)")
run("prompt: Aidan (21142)",         Employee_ID="21142")
run("prompt: Logan herself (21001)", Employee_ID="21001")
run("prompt: unknown ID (99999)",    Employee_ID="99999")