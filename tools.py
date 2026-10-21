"""
HR tools exposed over MCP.

Each tool: find the target -> check permission -> build the response.
Data comes from a backend (mock JSON or Workday tenant); permission
checks live in permissions.py. The model only ever sees what a tool returns.
"""
from typing import Annotated, Literal
from pydantic import Field

from backends import get_backend
from permissions import can_view, current_user

B = get_backend()
SEARCH_CAP = 25
TIME_OFF_PLANS = B.time_off_plans()                 # from the data, not hard-coded
PlanNameAsked = Literal[tuple(TIME_OFF_PLANS)]           # still an enum in the tool schema

import functools
from backends.base import PermissionDenied

def _source_denials(fn):
    """If the data source (e.g. Workday security) refuses, return a normal denial."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except PermissionDenied:
            return _deny("that information (the HR system's security does not allow it)")
    return wrapper

# ---------------------------------------------------------------- helpers (not tools)

def _deny(what: str) -> dict:
    return {"error": "permission_denied",
            "message": f"You don't have access to {what}."}


def _find_worker(query) -> dict:
    """Return one Worker, or an {"error": ...} dict for not found / ambiguous."""
    matches = B.find_workers(query)
    if not matches:
        return {"error": f"No worker found matching '{query}'."}
    if len(matches) > 1:
        return {
            "error": f"{len(matches)} workers match '{query}'. Ask which one, then retry with the workerId.",
            "candidates": [{"name": w["name"], "workerId": w["workerId"]} for w in matches[:10]],
        }
    return matches[0]


def _manager_name(worker: dict) -> str | None:
    mgr = B.get_worker(worker["managerId"]) if worker["managerId"] else None
    return mgr["name"] if mgr else None


# ---------------------------------------------------------------- tools
@_source_denials
def who_am_i() -> dict:
    """Return the signed-in user's name, workerId, job title and manager's workerId.
    Call this first whenever the user says I, me, my or mine."""
    viewer = current_user()
    if viewer is None:
        return _deny("employee information (no signed-in user)")
    return {
        "name": viewer["name"],
        "workerId": viewer["workerId"],
        "title": viewer["title"],
        "managerId": viewer["managerId"],
    }

@_source_denials
def get_worker(
        name: Annotated[str, Field(description="Full or partial name, or the workerId, of the employee, e.g. 'Carol Bahl' or '10011'.")]
    ) -> dict:
    """Look up one employee by name or workerId and return their job title, department,
    location, and their manager's name and workerId. Use this whenever the user
    asks about a specific person."""
    viewer = current_user()
    if viewer is None:
        return _deny("employee information (no signed-in user)")

    w = _find_worker(name)
    if "error" in w:
        return w
    if not can_view(viewer, w, "directory"):
        return _deny(f"{w['name']}'s profile")

    return {
        "name": w["name"],
        "workerId": w["workerId"],
        "title": w["title"],
        "department": w["department"],
        "location": w["location"],
        "manager": _manager_name(w),
        "managerId": w["managerId"],
    }

@_source_denials
def get_direct_reports(
        manager_name: Annotated[str, Field(description="Full or partial name, or the workerId, of the manager, e.g. 'Tom Davis' or '10003'.")],
    ) -> dict:
    """List all direct reports of a manager, given the manager's name or workerId.
    Returns each report's name, workerId and title. Use this whenever the user asks who is on a manager's team."""
    viewer = current_user()
    if viewer is None:
        return _deny("employee information (no signed-in user)")

    manager = _find_worker(manager_name)
    if "error" in manager:
        return manager
    if not can_view(viewer, manager, "directory"):
        return _deny(f"{manager['name']}'s profile")

    reports = [
        {"workerId": w["workerId"], "name": w["name"], "title": w["title"]}
        for w in B.direct_reports(manager["workerId"])
    ]
    return {
        "manager": manager["name"],
        "managerId": manager["workerId"],
        "count": len(reports),
        "reports": reports,
    }

@_source_denials
def get_time_off_balance(
        name: Annotated[str, Field(description="Full or partial name, or the workerId, of the employee, e.g. 'Carol Bahl' or '10011'.")]
    ) -> dict:
    """Look up one employee's time off balance for every plan, given their name or workerId.
    Use this whenever the user asks about a single person's time off."""
    viewer = current_user()
    if viewer is None:
        return _deny("employee information (no signed-in user)")

    worker = _find_worker(name)
    if "error" in worker:
        return worker
    if not can_view(viewer, worker, "time_off"):
        return _deny(f"{worker['name']}'s time off")

    balances = B.time_off_balances(worker["workerId"])
    units = {b["unit"] for b in balances}
    return {
        "name": worker["name"],
        "workerId": worker["workerId"],
        "unit": units.pop() if len(units) == 1 else "mixed",
        "time_off_balance": {b["plan"]: b["balance"] for b in balances},
    }

@_source_denials
def search_workers(
    department: Annotated[str, Field(description="The department to search in, e.g. 'Engineering'.")] = "",
    location: Annotated[str, Field(description="The location to search in, e.g. 'London'.")] = "",
    title: Annotated[str, Field(description="The job title to search for, e.g. 'Software Engineer'.")] = ""
) -> dict:
    """Search for workers by department, location and/or job title. Every filter you give must match.
    Returns name, workerId, title, department and location, at most 25 rows; 'count' is the full total.
    Use this whenever the user asks about employees in a department, location, or with a job title."""
    viewer = current_user()
    if viewer is None:
        return _deny("employee information (no signed-in user)")
    if not (department or location or title):
        return {"error": "Provide at least one of department, location or title."}

    matches = B.search(department, location, title)
    if not matches:
        titles = sorted({w["title"] for w in B.search("", "", "")})
        return {"count": 0, "returned": 0, "workers": [],
                "hint": "No matches. Job titles in use: " + ", ".join(titles)}

    return {
        "count": len(matches),
        "returned": min(len(matches), SEARCH_CAP),
        "workers": [
            {"name": w["name"], "workerId": w["workerId"], "title": w["title"],
             "department": w["department"], "location": w["location"]}
            for w in matches[:SEARCH_CAP]
        ],
    }

@_source_denials
def get_team_time_off(
    manager_name: Annotated[str, Field(description="Full or partial name, or the workerId, of the manager, e.g. 'Tom Davis' or '10003'.")],
    time_off_plan: Annotated[PlanNameAsked, Field(description="Which time-off plan to report on.")],
    threshold: Annotated[float | None, Field(description="Optional. If given, return only people with a balance strictly below this amount. Omit to return the whole team.")] = None,
    inclusive: Annotated[bool, Field(description="Optional. If true, return people with a balance equal to or below the threshold. Default is false (strictly below).")] = False
) -> dict:
    """Return the balance of one time-off plan for every direct report of a manager, sorted lowest first,
    with each person's workerId. Takes the manager's name or workerId directly; no need to look up the
    team first. Use for any question about a team's time off: who is low, who has the most, or the full list."""
    viewer = current_user()
    if viewer is None:
        return _deny("employee information (no signed-in user)")

    manager = _find_worker(manager_name)
    if "error" in manager:
        return manager
    if time_off_plan not in TIME_OFF_PLANS:
        return {"error": f"Invalid time off plan '{time_off_plan}'. Must be one of: {', '.join(TIME_OFF_PLANS)}."}

    team = B.direct_reports(manager["workerId"])
    if not all(can_view(viewer, w, "time_off") for w in team):
        return _deny(f"the time off of {manager['name']}'s team")

    rows, units = [], set()
    for w in team:
        for b in B.time_off_balances(w["workerId"]):
            if b["plan"] == time_off_plan:
                rows.append({"name": w["name"], "workerId": w["workerId"], "balance": b["balance"]})
                units.add(b["unit"])

    if threshold is not None:
        rows = [r for r in rows if (r["balance"] <= threshold if inclusive else r["balance"] < threshold)]
    rows.sort(key=lambda r: r["balance"])

    return {
        "manager": manager["name"],
        "managerId": manager["workerId"],
        "plan": time_off_plan,
        "unit": units.pop() if len(units) == 1 else ("mixed" if units else None),
        "threshold": threshold,
        "inclusive": inclusive,
        "team_size": len(team),
        "matched": len(rows),
        "workers": rows,
    }

@_source_denials
def get_compensation(
        name: Annotated[str, Field(description="Full or partial name, or the workerId, of the employee, e.g. 'Carol Bahl' or '10011'.")]
    ) -> dict:
    """Return one employee's current annual base pay and currency, given their name or workerId."""
    viewer = current_user()
    if viewer is None:
        return _deny("employee information (no signed-in user)")

    worker = _find_worker(name)
    if "error" in worker:
        return worker
    if not can_view(viewer, worker, "compensation"):
        return _deny(f"{worker['name']}'s compensation")

    pay = B.compensation(worker["workerId"])
    if pay is None:
        return {"error": f"No compensation record for {worker['name']}."}

    return {
        "name": worker["name"],
        "workerId": worker["workerId"],
        "annualBasePay": pay["annualBasePay"],
        "currency": pay["currency"],
    }