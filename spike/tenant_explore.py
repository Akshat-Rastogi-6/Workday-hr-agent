"""Spike 2: find where manager, reports, IDs and time off live."""
import os, json
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
SAMPLES = ROOT / "samples"
SAMPLES.mkdir(exist_ok=True)

rest = os.environ["WD_REST_URL"].rstrip("/")                      # .../ccx/api/v1/<tenant>
base = rest.split("/ccx/api/")[0] + "/ccx/api"                    # .../ccx/api
tenant = rest.rstrip("/").split("/")[-1]

def api(service: str) -> str:                                     # e.g. api("common/v1")
    return f"{base}/{service}/{tenant}"

def token() -> str:
    r = requests.post(os.environ["WD_TOKEN_URL"],
                      data={"grant_type": "refresh_token", "refresh_token": os.environ["WD_REFRESH_TOKEN"]},
                      auth=(os.environ["WD_CLIENT_ID"], os.environ["WD_CLIENT_SECRET"]), timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]

T = token()

def save(name: str, url: str, **params):
    r = requests.get(url, headers={"Authorization": f"Bearer {T}"}, params=params, timeout=30)
    print(f"{r.status_code}  {name:<22} {url.split(tenant)[-1]}  {params or ''}")
    if r.ok:
        (SAMPLES / f"{name}.json").write_text(json.dumps(r.json(), indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        print("     ", r.text[:200])
    return r.json() if r.ok else None

common = api("common/v1")
me = save("me", f"{common}/workers/me")
aidan = "693618e08cc11000cb2fc27ed9ca0001"                       # a non-manager from your list
org = "693618e08cc11000caf3e1db2e190000"                         # his org: R&D - Product 1

save("worker_detail",    f"{common}/workers/{aidan}")
save("search_name",      f"{common}/workers", search="Logan")
save("org_detail",       f"{common}/supervisoryOrganizations/{org}")
save("org_members",      f"{common}/supervisoryOrganizations/{org}/workers")
save("me_orgs_managed",  f"{common}/workers/{me['id']}/supervisoryOrganizationsManaged")
save("time_off_details", f"{common}/workers/{aidan}/timeOffDetails")
save("absence_balances", f"{api('absenceManagement/v1')}/balances", worker=aidan)
save("staffing_worker",  f"{api('staffing/v6')}/workers/{aidan}")

absence4 = api("absenceManagement/v4")
save("v4_time_off_me",   f"{absence4}/workers/me/timeOffDetails", limit=5)
save("v4_balances",      f"{absence4}/balances", worker=aidan)

# The Employee ID test. Replace 21002 with a real Employee ID once summarize shows one.
save("by_employee_id",   f"{common}/workers/Employee_ID=21002")

stephanie = "693618e08cc11000cb2f1e133cad0001"     # manager of R&D - Product 1

save("astor_detail",       f"{common}/workers/{stephanie}")
save("astor_direct",       f"{common}/workers/{stephanie}/directReports")
save("aidan_by_empid",     f"{common}/workers/Employee_ID=21142")
save("search_partial",     f"{common}/workers", search="Log")
save("balances_all",       f"{api('absenceManagement/v1')}/balances", limit=100)
save("staffing_org",       f"{api('staffing/v6')}/supervisoryOrganizations/{org}")