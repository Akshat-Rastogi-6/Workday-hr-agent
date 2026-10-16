"""
Tools the LLM can ask for.

A "tool" is three things basically:

1. A normal python function         -> get_worker()
2. a description the model can read -> GET_WORKER_SCHEMA
3. a way to run it by name          -> run_tool()

The model never runs this code. It only reads the schema and replies with
"please call get_worker with these arguments". Your program does the calling.

People are identified in two ways:
- workerId (e.g. "10011"): short, shown to the model, accepted by every tool.
- id (32-char hex): internal key used by the data files. Tools join on this,
  never on names, because names can be duplicated or mangled.
"""

import json
from pathlib import Path
from typing import Annotated, Literal
from pydantic import Field

WORKERS = json.loads(Path("data/workers.json").read_text(encoding="utf-8"))["data"]
TIME_OFF_BALANCES = json.loads(Path("data/time_off_balances.json").read_text(encoding="utf-8"))["data"]

# Lookup table: internal id -> full worker record. Built once at startup.
WORKERS_BY_ID = {w["id"]: w for w in WORKERS}

TIME_OFF_PLANS = ["Vacation", "Sick Leave", "Floating Holiday"]
SEARCH_CAP = 25


# 1. The functions -> plain Python, no AI involved.

def _find_worker(query) -> dict:
    """Internal helper (not a tool). Return the raw worker record, or an {"error": ...} dict.

    Digits only -> exact match on workerId. Anything else -> case-insensitive partial name match.
    """
    query = str(query).strip()

    if query.isdigit():
        matches = [w for w in WORKERS if w["workerId"] == query]
    else:
        matches = [w for w in WORKERS if query.lower() in w["descriptor"].lower()]

    if not matches:
        return {"error": f"No worker found matching '{query}'."}
    if len(matches) > 1:
        # Tell the model what went wrong so it can ask the user or retry.
        return {
            "error": f"{len(matches)} workers match '{query}'. Ask which one, then retry with the workerId.",
            "candidates": [{"name": w["descriptor"], "workerId": w["workerId"]} for w in matches[:10]],
        }
    return matches[0]


def _worker_id_of(ref: dict | None) -> str | None:
    """Turn a {id, descriptor} reference (e.g. a manager field) into a workerId."""
    if not ref:
        return None
    return WORKERS_BY_ID[ref["id"]]["workerId"]


def get_worker(
        name: Annotated[str, Field(description="Full or partial name, or the workerId, of the employee, e.g. 'Carol Bahl' or '10011'.")]
    ) -> dict:
    """Look up one employee by name or workerId and return their job title, department,
    location, hire date, and their manager's name and workerId. Use this whenever the user
    asks about a specific person."""
    w = _find_worker(name)
    if "error" in w:
        return w

    return {
        "name": w["descriptor"],
        "workerId": w["workerId"],
        "title": w["businessTitle"],
        "department": w["primarySupervisoryOrganization"]["descriptor"],
        "location": w["location"]["descriptor"],
        "hireDate": w["hireDate"],
        "manager": w["manager"]["descriptor"] if w["manager"] else None,
        "managerId": _worker_id_of(w["manager"]),
    }


def get_direct_reports(
        manager_name: Annotated[str, Field(description="Full or partial name, or the workerId, of the manager, e.g. 'Tom Davis' or '10003'.")],
    ) -> dict:
    """List all direct reports of a manager, given the manager's name or workerId.
    Returns each report's name, workerId and title. Use this whenever the user asks who is on a manager's team."""
    manager = _find_worker(manager_name)
    if "error" in manager:
        return manager  # pass the error along

    reports = [
        {
            "workerId": w["workerId"],
            "name": w["descriptor"],
            "title": w["businessTitle"],
        }
        for w in WORKERS
        if w["manager"] and w["manager"]["id"] == manager["id"]
    ]
    return {
        "manager": manager["descriptor"],
        "managerId": manager["workerId"],
        "count": len(reports),
        "reports": reports,
    }


def get_time_off_balance(
        name: Annotated[str, Field(description="Full or partial name, or the workerId, of the employee, e.g. 'Carol Bahl' or '10011'.")]
    ) -> dict:
    """Look up one employee's time off balance for every plan, given their name or workerId.
    Use this whenever the user asks about a single person's time off."""
    worker = _find_worker(name)
    if "error" in worker:
        return worker

    balance = {
        row["timeOffPlan"]: row["balance"]
        for row in TIME_OFF_BALANCES
        if row["worker"]["id"] == worker["id"]
    }

    return {
        "name": worker["descriptor"],
        "workerId": worker["workerId"],
        "unit": "Days",
        "time_off_balance": balance,
    }


def search_workers(
    department: Annotated[str, Field(description="The department to search in, e.g. 'Engineering'.")] = "",
    location: Annotated[str, Field(description="The location to search in, e.g. 'London'.")] = "",
    title: Annotated[str, Field(description="The job title to search for, e.g. 'Software Engineer'.")] = ""
) -> dict:
    """Search for workers by department, location and/or job title. Every filter you give must match.
    Returns name, workerId, title, department and location, at most 25 rows; 'count' is the full total.
    Use this whenever the user asks about employees in a department, location, or with a job title."""
    if not (department or location or title):
        return {"error": "Provide at least one of department, location or title."}

    matches = [
        w for w in WORKERS
        if (not department or department.lower() in w["primarySupervisoryOrganization"]["descriptor"].lower())
        and (not location or location.lower() in w["location"]["descriptor"].lower())
        and (not title or title.lower() in w["businessTitle"].lower())
    ]

    if not matches:
        titles = sorted({w["businessTitle"] for w in WORKERS})
        return {"count": 0, "returned": 0, "workers": [],
                "hint": "No matches. Job titles in use: " + ", ".join(titles)}

    return {
        "count": len(matches),
        "returned": min(len(matches), SEARCH_CAP),
        "workers": [
            {
                "name": w["descriptor"],
                "workerId": w["workerId"],
                "title": w["businessTitle"],
                "department": w["primarySupervisoryOrganization"]["descriptor"],
                "location": w["location"]["descriptor"],
            }
            for w in matches[:SEARCH_CAP]
        ],
    }


def get_team_time_off(
    manager_name: Annotated[str, Field(description="Full or partial name, or the workerId, of the manager, e.g. 'Tom Davis' or '10003'.")],
    time_off_plan: Annotated[Literal["Vacation", "Sick Leave", "Floating Holiday"], Field(description="Which time-off plan to report on.")],
    threshold: Annotated[float | None, Field(description="Optional. If given, return only people with a balance strictly below this many days. Omit to return the whole team.")] = None,
    inclusive: Annotated[bool, Field(description="Optional. If true, return people with a balance equal to or below the threshold. Default is false (strictly below).")] = False
) -> dict:
    """Return the balance of one time-off plan for every direct report of a manager, sorted lowest first,
    with each person's workerId. Takes the manager's name or workerId directly; no need to look up the
    team first. Use for any question about a team's time off: who is low, who has the most, or the full list."""
    manager = _find_worker(manager_name)
    if "error" in manager:
        return manager

    if time_off_plan not in TIME_OFF_PLANS:
        return {"error": f"Invalid time off plan '{time_off_plan}'. Must be one of: {', '.join(TIME_OFF_PLANS)}."}

    # Internal ids of the manager's direct reports.
    team = {
        w["id"] for w in WORKERS
        if w["manager"] and w["manager"]["id"] == manager["id"]
    }

    rows = [
        {
            "name": b["worker"]["descriptor"],
            "workerId": WORKERS_BY_ID[b["worker"]["id"]]["workerId"],
            "balance": b["balance"],
        }
        for b in TIME_OFF_BALANCES
        if b["worker"]["id"] in team and b["timeOffPlan"] == time_off_plan
    ]

    if threshold is not None:
        if inclusive:
            rows = [r for r in rows if r["balance"] <= threshold]
        else:
            rows = [r for r in rows if r["balance"] < threshold]

    rows.sort(key=lambda r: r["balance"])

    return {
        "manager": manager["descriptor"],
        "managerId": manager["workerId"],
        "plan": time_off_plan,
        "unit": "Days",
        "threshold": threshold,
        "team_size": len(team),
        "matched": len(rows),
        "workers": rows,
        "inclusive": inclusive,
    }

# No Longer needed as the MCP server handles this now. The model never runs this code. It only reads the schema and replies with "please call get_worker with these arguments". Your program does the calling.


# 2. The schemas -> this text is ALL the model knows about each function.

# GET_WORKER_SCHEMA = {
#     "name": "get_worker",
#     "description": (
#         "Look up one employee by name or workerId and return their job title, department, "
#         "location, hire date, and their manager's name and workerId. Use this whenever the user "
#         "asks about a specific person."
#     ),
#     "parameters": {
#         "type": "object",
#         "properties": {
#             "name": {
#                 "type": "string",
#                 "description": "Full or partial name, or the workerId, of the employee, e.g. 'Carol Bahl' or '10011'.",
#             }
#         },
#         "required": ["name"],
#     },
# }

# GET_DIRECT_REPORTS_SCHEMA = {
#     "name": "get_direct_reports",
#     "description": (
#         "List all direct reports of a manager, given the manager's name or workerId. "
#         "Returns each report's name, workerId and title. Use this whenever the user asks who is on a manager's team."
#     ),
#     "parameters": {
#         "type": "object",
#         "properties": {
#             "manager_name": {
#                 "type": "string",
#                 "description": "Full or partial name, or the workerId, of the manager, e.g. 'Tom Davis' or '10003'.",
#             }
#         },
#         "required": ["manager_name"],
#     },
# }

# GET_TIME_OFF_BALANCE_SCHEMA = {
#     "name": "get_time_off_balance",
#     "description": (
#         "Look up one employee's time off balance for every plan, given their name or workerId. "
#         "Use this whenever the user asks about a single person's time off."
#     ),
#     "parameters": {
#         "type": "object",
#         "properties": {
#             "name": {
#                 "type": "string",
#                 "description": "Full or partial name, or the workerId, of the employee, e.g. 'Carol Bahl' or '10011'.",
#             }
#         },
#         "required": ["name"],
#     },
# }

# GET_SEARCH_WORKERS_SCHEMA = {
#     "name": "search_workers",
#     "description": (
#         "Search for workers by department, location and/or job title. Every filter you give must match. "
#         "Returns name, workerId, title, department and location, at most 25 rows; 'count' is the full total. "
#         "Use this whenever the user asks about employees in a department, location, or with a job title."
#     ),
#     "parameters": {
#         "type": "object",
#         "properties": {
#             "department": {
#                 "type": "string",
#                 "description": "Full or partial department name, e.g. 'Engineering'.",
#             },
#             "location": {
#                 "type": "string",
#                 "description": "Full or partial location name, e.g. 'London'.",
#             },
#             "title": {
#                 "type": "string",
#                 "description": "Full or partial job title, e.g. 'Software Engineer'.",
#             },
#         },
#         "required": [],
#     },
# }

# GET_TEAM_TIME_OFF_SCHEMA = {
#     "name": "get_team_time_off",
#     "description": (
#         "Return the balance of one time-off plan for every direct report of a manager, sorted lowest first, "
#         "with each person's workerId. Takes the manager's name or workerId directly; no need to look up the team first. "
#         "Use for any question about a team's time off: who is low, who has the most, or the full list."
#     ),
#     "parameters": {
#         "type": "object",
#         "properties": {
#             "manager_name": {
#                 "type": "string",
#                 "description": "Full or partial name, or the workerId, of the manager, e.g. 'Tom Davis' or '10003'.",
#             },
#             "time_off_plan": {
#                 "type": "string",
#                 "enum": TIME_OFF_PLANS,
#                 "description": "Which time-off plan to report on.",
#             },
#             "threshold": {
#                 "type": "number",
#                 "description": "Optional. If given, return only people with a balance strictly below this many days. Omit to return the whole team.",
#             },
#         },
#         "required": ["manager_name", "time_off_plan"],
#     },
# }


# 3. The dispatcher -> maps the name the model asks for to the real function.

# TOOLS = {
#     "get_worker": get_worker,
#     "get_direct_reports": get_direct_reports,
#     "get_time_off_balance": get_time_off_balance,
#     "search_workers": search_workers,
#     "get_team_time_off": get_team_time_off,
# }


# def run_tool(name: str, arguments: dict) -> str:
#     if name not in TOOLS:
#         return json.dumps({"error": f"Unknown tool '{name}'."})
#     return json.dumps(TOOLS[name](**arguments), ensure_ascii=False)


if __name__ == "__main__":
    # Pretend to be the model: these are the requests it would send back.

    # print("--- get_worker ---")
    print(run_tool("get_worker", {"name": "Carol Bahl"}))
    # print(run_tool("get_worker", {"name": "10011"}))               # by ID
    # print(run_tool("get_worker", {"name": 10011}))                 # ID sent as a number
    # print(run_tool("get_worker", {"name": "an"})[:300])            # ambiguous: candidates with IDs
    # print(run_tool("get_worker", {"name": "Zzyzx"}))               # not found

    # print("--- get_direct_reports ---")
    # print(run_tool("get_direct_reports", {"manager_name": "Tom Davis"})[:300])
    # print(run_tool("get_direct_reports", {"manager_name": "10003"})[:300])   # by ID
    # print(run_tool("get_direct_reports", {"manager_name": "Carol Bahl"}))    # no reports

    # print("--- get_time_off_balance ---")
    # print(run_tool("get_time_off_balance", {"name": "Carol Bahl"}))
    # print(run_tool("get_time_off_balance", {"name": "10011"}))

    # print("--- search_workers ---")
    # print(run_tool("search_workers", {"department": "Finance", "location": "London"})[:300])
    # r = json.loads(run_tool("search_workers", {"department": "Engineering"}))
    # print("count", r["count"], "returned", r["returned"], "rows", len(r["workers"]))
    # print(run_tool("search_workers", {}))

    # print("--- get_team_time_off ---")
    # print(run_tool("get_team_time_off", {"manager_name": "Tom Davis", "time_off_plan": "Vacation", "threshold": 5}))
    print(run_tool("get_team_time_off", {"manager_name": "Tom Davis", "time_off_plan": "Vacation"}))
    # print(run_tool("get_team_time_off", {"manager_name": "Carol Bahl", "time_off_plan": "Vacation"}))
    # print(run_tool("get_team_time_off", {"manager_name": "Tom Davis", "time_off_plan": "Vacations"}))
    # print(run_tool("get_team_time_off", {"manager_name": "Zzyzx", "time_off_plan": "Vacation"}))