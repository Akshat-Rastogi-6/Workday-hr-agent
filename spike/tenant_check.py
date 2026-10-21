"""Smoke test: token + every endpoint the tenant backend will use, with expected results."""
import os
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

rest = os.environ["WD_REST_URL"].rstrip("/")
base = rest.split("/ccx/api/")[0] + "/ccx/api"
tenant = rest.split("/")[-1]

def api(service: str) -> str:
    return f"{base}/{service}/{tenant}"

# ---- token
r = requests.post(
    os.environ["WD_TOKEN_URL"],
    data={"grant_type": "refresh_token", "refresh_token": os.environ["WD_REFRESH_TOKEN"]},
    auth=(os.environ["WD_CLIENT_ID"], os.environ["WD_CLIENT_SECRET"]),
    timeout=30,
)
print(f"{r.status_code}  token")
r.raise_for_status()
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

results = []

def check(label: str, expect: int, url: str, **params):
    resp = requests.get(url, headers=H, params=params, timeout=30)
    ok = resp.status_code == expect
    results.append(ok)
    print(f"{'OK  ' if ok else 'BAD '} {resp.status_code} (want {expect})  {label}")
    if not ok:
        print("        ", resp.text[:150])
    return resp.json() if resp.ok else None

common = api("common/v1")
absence = api("absenceManagement/v4")
AIDAN = "Employee_ID=21142"
ASTOR = "693618e08cc11000cb2f1e133cad0001"      # Stephanie Astor (WID); Logan is not her manager

# ---- directory
me = check("who am I                  workers/me",                    200, f"{common}/workers/me")
check(     "by Employee ID            workers/Employee_ID=21142",     200, f"{common}/workers/{AIDAN}")
check(     "search                    workers?search=Log",            200, f"{common}/workers", search="Log")
check(     "staffing (workerId)       staffing/v6 workers/{AIDAN}",   200, f"{api('staffing/v6')}/workers/{AIDAN}")

# ---- org structure
if me:
    org = me["primarySupervisoryOrganization"]["id"]
    check( "my org + its manager      supervisoryOrganizations/{org}", 200, f"{common}/supervisoryOrganizations/{org}")
check(     "orgs I manage             workers/me/supervisoryOrganizationsManaged", 200,
           f"{common}/workers/me/supervisoryOrganizationsManaged")

# ---- direct reports: the security-domain test
check(     "MY direct reports         workers/me/directReports",      200, f"{common}/workers/me/directReports")
check(     "ASTOR's direct reports    (not my team -> denied)",       403, f"{common}/workers/{ASTOR}/directReports")

# ---- time off
check(     "balances by Employee ID   absenceManagement/v4/balances", 200, f"{absence}/balances", worker=AIDAN)
check(     "time off entries          workers/me/timeOffDetails",     200, f"{absence}/workers/me/timeOffDetails", limit=5)

check("pay via RaaS              CR_-__Compensation (Aidan)", 200,
      os.environ["WD_RAAS_COMP_URL"], Employee_ID="21142", format="json")

print(f"\n{sum(results)}/{len(results)} as expected")