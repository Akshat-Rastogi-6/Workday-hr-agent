"""
Build evals/cases_tenant.json from the LIVE Workday tenant.

Expected values come from the raw REST/RaaS endpoints, called directly here,
NOT through backends/workday.py. If the backend has a mapping bug, the eval
catches it instead of inheriting it.

Live data moves (time off accrues), so re-run this right before each eval run:
    python evals/build_cases_tenant.py
    EVAL_CASES=cases_tenant.json WORKDAY_BACKEND=tenant python evals/run_evals.py
"""
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "cases_tenant.json"
load_dotenv(ROOT / ".env")

ANCHOR = "Aidan Mitzner"      # an employee outside the signed-in user's chain
PTO = "Paid Time Off"         # the tenant's plan that "vacation" draws from

# ---------------------------------------------------------------- raw API (read-only)

rest = os.environ["WD_REST_URL"].rstrip("/")
BASE = rest.split("/ccx/api/")[0] + "/ccx/api"
TENANT = rest.split("/")[-1]


def url(service, path):
    return f"{BASE}/{service}/{TENANT}/{path.lstrip('/')}"


_tok = requests.post(
    os.environ["WD_TOKEN_URL"],
    data={"grant_type": "refresh_token", "refresh_token": os.environ["WD_REFRESH_TOKEN"]},
    auth=(os.environ["WD_CLIENT_ID"], os.environ["WD_CLIENT_SECRET"]),
    timeout=30,
)
_tok.raise_for_status()
H = {"Authorization": f"Bearer {_tok.json()['access_token']}"}


def get(u, **params):
    r = requests.get(u, headers=H, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def get_all(u, **params):
    out, offset = [], 0
    while True:
        body = get(u, limit=100, offset=offset, **params)
        page = body.get("data", [])
        out += page
        offset += len(page)
        if not page or offset >= body.get("total", 0):
            return out


def employee_id(wid):
    return get(url("staffing/v6", f"workers/{wid}"))["workerId"]


def org_manager(org_id):
    return get(url("common/v1", f"supervisoryOrganizations/{org_id}")).get("manager")


def pto_of(emp_id):
    rows = get_all(url("absenceManagement/v4", "balances"), worker=f"Employee_ID={emp_id}")
    for b in rows:
        if b["absencePlan"]["descriptor"] == PTO:
            return float(b["quantity"])
    raise SystemExit(f"No '{PTO}' balance for {emp_id}")


def pay_of(emp_id):
    rows = get(os.environ["WD_RAAS_COMP_URL"], Employee_ID=emp_id, format="json").get("Report_Entry", [])
    if len(rows) != 1:
        raise SystemExit(f"Expected 1 pay row for {emp_id}, got {len(rows)}")
    return f"{float(rows[0]['Total_Base_Pay_Annualized_-_Amount']):.0f}", rows[0]["Total_Base_Pay_Annualized_-_Currency"]


def whole(x):
    """150.0 -> '150', 190.73 -> '190'. Matches however the model rounds the decimals."""
    return str(int(x))


def find_one(name):
    hits = [w for w in get_all(url("common/v1", "workers"), search=name) if w["descriptor"] == name]
    if len(hits) != 1:
        raise SystemExit(f"Expected exactly one '{name}', got {len(hits)}")
    return hits[0]


# ---------------------------------------------------------------- facts from the tenant

me_raw = get(url("common/v1", "workers/me"))
ME = employee_id(me_raw["id"])

my_reports = get_all(url("common/v1", "workers/me/directReports"))
if len(my_reports) < 2:
    raise SystemExit("The signed-in user needs at least 2 direct reports for the team cases.")
report_ids = {r["descriptor"]: employee_id(r["id"]) for r in my_reports}

anchor = find_one(ANCHOR)
anchor_id = employee_id(anchor["id"])
anchor_org = get(url("common/v1", f"workers/{anchor['id']}"))["primarySupervisoryOrganization"]

mgr = org_manager(anchor_org["id"])                                   # e.g. Stephanie Astor
mgr_org = get(url("common/v1", f"workers/{mgr['id']}"))["primarySupervisoryOrganization"]
mgr_mgr = org_manager(mgr_org["id"])                                  # e.g. James Brooks

org_members = [w["descriptor"] for w in get_all(url("common/v1", f"supervisoryOrganizations/{anchor_org['id']}/workers"))]

dept = anchor_org["descriptor"]
dept_count = sum(
    1 for w in get_all(url("common/v1", "workers"))
    if dept.lower() in (w.get("primarySupervisoryOrganization") or {}).get("descriptor", "").lower()
)

team_pto = sorted(((pto_of(eid), name) for name, eid in report_ids.items()))
if team_pto[0][0] == team_pto[1][0]:
    raise SystemExit("Tie for lowest PTO on the signed-in user's team.")

if get(url("common/v1", "workers"), search="Zara Quintrell").get("total", 0) != 0:
    raise SystemExit("'Zara Quintrell' unexpectedly exists in the tenant.")

anchor_pay, anchor_cur = pay_of(anchor_id)
first_report = sorted(report_ids)[0]
report_pay, _ = pay_of(report_ids[first_report])

# ---------------------------------------------------------------- cases

cases = []


def add(**case):
    case.setdefault("category", "tenant")
    case.setdefault("as_user", ME)
    case.setdefault("must_contain", [])
    case.setdefault("must_not_contain", [])
    cases.append(case)


add(id="tenant-own-pto",
    question="How much paid time off do I have?",
    must_contain=[whole(pto_of(ME)), "hour"],
    expect_tools=["who_am_i", "get_time_off_balance"], max_calls=2)

add(id="tenant-vacation-synonym",
    question=f"How much vacation does {ANCHOR} have?",
    must_contain=[whole(pto_of(anchor_id)), "hour"],
    must_not_contain=["no vacation", "don't have a vacation", "does not have a vacation"],
    max_calls=2)

add(id="tenant-my-team",
    question="Who is on my team?",
    must_contain=sorted(report_ids),
    expect_tools=["get_direct_reports"], max_calls=2)

add(id="tenant-skip-level",
    question=f"Who is {ANCHOR}'s manager's manager?",
    must_contain=[mgr_mgr["descriptor"]],
    max_calls=3)

add(id="tenant-pay-allowed",
    question=f"What does {ANCHOR} earn?",
    must_contain=[anchor_pay, anchor_cur],
    expect_tools=["get_compensation"], max_calls=2)

add(id="tenant-pay-own-report",
    question=f"What does {first_report} earn?",
    must_contain=[report_pay],
    expect_tools=["get_compensation"], max_calls=2)

add(id="tenant-denied-reports",              # Workday's own security (Reports: Manager), not can_view
    question=f"Who reports to {mgr['descriptor']}?",
    must_contain=["access"],
    must_not_contain=[m for m in org_members if m != mgr["descriptor"]],
    max_calls=2)

add(id="tenant-dept-count",
    question=f"How many people work in {dept}?",
    must_contain=[str(dept_count)],
    expect_tools=["search_workers"], max_calls=2)

add(id="tenant-not-found",
    question="How much time off does Zara Quintrell have?",
    must_contain=["Zara Quintrell"],
    must_not_contain=["hour"],
    max_calls=2)

add(id="tenant-team-least-pto",
    question="Who on my team has the least paid time off left?",
    must_contain=[team_pto[0][1]],
    must_not_contain=[team_pto[1][1]],
    expect_tools=["get_team_time_off"], max_calls=3)

# ---------------------------------------------------------------- write + summary

OUT.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Signed-in user: {me_raw['descriptor']} ({ME})")
print(f"Wrote {len(cases)} cases to {OUT}\n")
for c in cases:
    print(f"[{c['id']}]  Q: {c['question']}")
    if c["must_contain"]:
        print(f"    must contain:     {c['must_contain']}")
    if c["must_not_contain"]:
        print(f"    must NOT contain: {c['must_not_contain']}")