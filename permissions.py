"""Who is asking, and what are they allowed to see.

Works on the shared Worker shape from backends.base, so it is the same
for every backend (mock today, Workday tenant later).
"""
import os

from backends import get_backend

DOMAINS = {"directory", "time_off", "compensation"}
HR_TITLES = set(t.strip() for t in os.getenv("HR_TITLES", "HR Partner").split(",") if t.strip())


def current_user() -> dict | None:
    """The signed-in user's Worker.
    Mock: from WORKDAY_USER. Tenant: from the token (WORKDAY_USER must match it, or nobody is signed in)."""
    backend = get_backend()
    claimed = os.getenv("WORKDAY_USER")
    actual = backend.current_user_id()            # None for the mock
    if actual is not None:
        if claimed and claimed != actual:
            return None                            # --as disagrees with the token: fail closed
        return backend.get_worker(actual)
    if not claimed:
        return None
    return backend.get_worker(claimed)


def managers_above(worker: dict) -> list[str]:
    """workerIds of everyone above this worker: manager, manager's manager, ... up to the top.
    Stops on a loop or a missing manager record."""
    backend = get_backend()
    out, seen = [], set()
    manager_id = worker.get("managerId")
    while manager_id:
        if manager_id in seen:
            break
        manager = backend.get_worker(manager_id)
        if manager is None:
            break
        seen.add(manager_id)
        out.append(manager_id)
        manager_id = manager.get("managerId")
    return out


def can_view(viewer: dict | None, target: dict, domain: str) -> bool:
    """Directory: any signed-in user. Time off / compensation: self, anyone above
    the target in the chain, or HR. Unknown domain or no user -> False."""
    if viewer is None or domain not in DOMAINS:
        return False
    if viewer["workerId"] == target["workerId"]:
        return True
    if domain == "directory":
        return True
    if domain in ("time_off", "compensation"):
        return viewer["title"] in HR_TITLES or viewer["workerId"] in managers_above(target)
    return False


if __name__ == "__main__":
    b = get_backend()
    stephanie = b.get_worker("10006")     # Stephanie Richardson
    tom       = b.get_worker("10003")     # her manager
    leanne    = b.get_worker("10002")     # Tom's manager
    hr        = b.get_worker("10126")     # Frank Bal, HR Partner
    other_mgr = b.get_worker("10005")     # Gotthold Klapp, a different team

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
    me = current_user()
    print("OK  " if me and me["name"] == "Stephanie Richardson" else "FAIL", "current_user by workerId")
    os.environ["WORKDAY_USER"] = "99999"
    print("OK  " if current_user() is None else "FAIL", "unknown user, fail closed")
    os.environ.pop("WORKDAY_USER", None)
    print("OK  " if current_user() is None else "FAIL", "no WORKDAY_USER, fail closed")