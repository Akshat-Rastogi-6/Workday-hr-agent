"""Who is asking, and what are they allowed to see."""
import os
from data import WORKERS, WORKERS_BY_ID

DOMAINS = {"directory", "time_off", "compensation"}
HR_TITLES = {"HR Partner"}

def current_user() -> dict | None:
    """Read the workerId from the WORKDAY_USER env var and return that worker's raw record.
    Return None if it's unset or doesn't match anyone (fail closed)."""
    worker_id = os.getenv("WORKDAY_USER")
    return next((w for w in WORKERS if w["workerId"] == worker_id), None)

def managers_above(worker: dict) -> list[str]:
    out, seen = [], set()
    while worker.get("manager"):
        manager_id = worker["manager"]["id"]
        if manager_id in seen or manager_id not in WORKERS_BY_ID:
            break
        seen.add(manager_id)
        out.append(manager_id)
        worker = WORKERS_BY_ID[manager_id]
    return out

def can_view(viewer: dict | None, target: dict, domain: str) -> bool:
    """domain is "directory", "time_off" or "compensation". Implement the table above.
    Unknown domain -> False."""
    if viewer is None or domain not in DOMAINS:
        return False
    if viewer["id"] == target["id"]:
        return True
    if domain == "directory":
        return True
    if domain in ("time_off", "compensation"):
        return viewer["businessTitle"] in HR_TITLES or viewer["id"] in managers_above(target)
    return False

if __name__ == "__main__":
    from tools import _find_worker
    # Find workers by their IDs or names
    stephanie = _find_worker("10006")       # Stephanie Richardson
    tom       = _find_worker("10003")     # her manager
    leanne    = _find_worker("10002")     # Tom's manager
    hr        = _find_worker("10126")       # any HR Partner
    other_mgr = _find_worker("10005")     # Gotthold Klapp, a different team

    checks = [
        (can_view(stephanie, stephanie, "time_off"),     True,  "self"),
        (can_view(stephanie, tom, "time_off"),           False, "up the chain"),
        (can_view(tom, stephanie, "time_off"),           True,  "direct report"),
        (can_view(leanne, stephanie, "compensation"),    True,  "indirect report"),
        (can_view(other_mgr, stephanie, "time_off"),     False, "other team"),
        (can_view(stephanie, leanne, "directory"),       True,  "directory is public"),
        (can_view(hr, leanne, "compensation"),           True,  "HR sees all"),
        (can_view(None, stephanie, "time_off"),          False, "no user, fail closed"),
        (can_view(None, stephanie, "directory"),         False, "no user, fail closed"),
        (can_view(tom, stephanie, "salary_history"),     False, "unknown domain"),
        (can_view(stephanie, stephanie, "nationalId"),   False, "self, unknown domain"),
        (can_view(hr, stephanie, "time_off"),            True,  "HR sees time off"),
        (can_view(stephanie, hr, "time_off"),            False, "employee can't see HR"),
    ]
    for got, want, label in checks:
        print("OK  " if got == want else "FAIL", label)

    os.environ["WORKDAY_USER"] = "10006"
    print("OK  " if current_user() and current_user()["descriptor"] == "Stephanie Richardson" else "FAIL", "current_user by workerId")
    os.environ["WORKDAY_USER"] = "99999"
    print("OK  " if current_user() is None else "FAIL", "unknown user, fail closed")
