import os
from tools import get_worker, get_time_off_balance, get_team_time_off, get_compensation

def as_user(worker_id):
    if worker_id is None:
        os.environ.pop("WORKDAY_USER", None)
    else:
        os.environ["WORKDAY_USER"] = worker_id

def denied(r):  return r.get("error") == "permission_denied"
def allowed(r): return "error" not in r          # real data came back, no error of any kind

checks = []
as_user("10006")   # Stephanie, employee
own_comp = get_compensation("10006")
checks += [
    (allowed(get_time_off_balance("10006")),               "employee: own balance"),
    (denied(get_time_off_balance("10003")),                "employee: manager's balance"),
    ("annualBasePay" in own_comp and "nationalId" not in own_comp, "own comp: pay shown, nationalId hidden"),
    (denied(get_compensation("10003")),                    "employee: manager's comp"),
    (denied(get_team_time_off("10003", "Vacation")),       "employee: someone else's team"),
    ("error" in get_time_off_balance("Zzyzx") and not denied(get_time_off_balance("Zzyzx")),
                                                           "not found: error, no crash"),
    ("candidates" in get_compensation("Andy"),             "ambiguous: returns candidates"),
]
as_user("10003")   # Tom, manager
checks += [
    (allowed(get_team_time_off("10003", "Vacation")),      "manager: own team"),
    (allowed(get_compensation("10006")),                   "manager: report's comp"),
    (denied(get_compensation("10002")),                    "manager: boss's comp"),
]
as_user("10002")   # Leanne, manager's manager
checks += [
    (allowed(get_team_time_off("10003", "Vacation")),      "skip-level: Tom's team"),
]
as_user("10126")   # HR Partner
checks += [
    (allowed(get_compensation("10002")),                   "HR: anyone's comp"),
]
as_user(None)      # nobody
checks += [
    (denied(get_worker("10006")),                          "no user: directory denied"),
]
for ok, label in checks:
    print("OK  " if ok else "FAIL", label)