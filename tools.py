"""
One tool the LLM can ask for.

A "tool" is three things bascially"

1. A normal python function         -> get_worker()
2. a description the model can read -> GET_WORKER_SCHEMA
3. a way to run it by name          -> run_tool()

The model never runs this code. It only reads the schema and replies with
"please call get_worker with these arguments". Your program does the calling.
"""

import json
from pathlib import Path

WORKERS = json.loads(Path("data/workers.json").read_text())["data"]
TIME_OFF_BALANCES = json.loads(Path("data/time_off_balances.json").read_text())["data"]


#1. The Funtion -> A simple Python funtion with no AI involved.

def get_worker(name: str) -> dict:
    """Find a worker by full or partial name (case insensitive)."""
    matches = [w for w in WORKERS if name.lower() in w["descriptor"].lower()]

    if not matches:
        return {"error": f"No worker found matching '{name}'."}
    if len(matches) > 1:
        # Tell the model what went wrong so it can ask the user or retry.
        return {
            "error": f"{len(matches)} workers match '{name}'. Ask which one.",
            "candidates": [w["descriptor"] for w in matches[:10]],
        }

    w = matches[0]
    return {
        "name": w["descriptor"],
        "workerId": w["workerId"],
        "title": w["businessTitle"],
        "department": w["primarySupervisoryOrganization"]["descriptor"],
        "location": w["location"]["descriptor"],
        "hireDate": w["hireDate"],
        "manager": w["manager"]["descriptor"] if w["manager"] else None,
    }


def get_direct_reports(manager_name: str) -> dict:
    """ Find all the workers name and title who reports to a given manager by name (case insensitive)."""
    manager = get_worker(manager_name)
    if "error" in manager:
        return manager  # pass the error along
    
    reports = [
        {
            "name": w["descriptor"],
            "title": w["businessTitle"]
        }
        for w in WORKERS 
        if w["manager"] and w["manager"]["descriptor"] == manager["name"]
    ]
    return {
        "manager": manager["name"],
        "count": len(reports),
        "reports": reports
    }

def get_time_off_balance(name: str) -> dict:
    " Find the time off balance for a given employee by name (case insensitive)."
    worker = get_worker(name)
    if "error" in worker:
        return worker

    balance = {
        row["timeOffPlan"]: row["balance"]
        for row in TIME_OFF_BALANCES
        if row["worker"]["descriptor"] == worker["name"]
    }

    return {
        "name": worker["name"],
        "unit": "Days",
        "time_off_balance": balance
    }

def search_workers(department: str = "", location: str = "", title: str = "") -> dict:
    """ Search for workers by department or location or title (case insensitive)."""

    if not (department or location or title): return {"error": "Provide at least one of department, location or title."}

    matches = [
        w for w in WORKERS
        if (not department or department.lower() in w["primarySupervisoryOrganization"]["descriptor"].lower())
        and (not location or location.lower() in w["location"]["descriptor"].lower())
        and (not title or title.lower() in w["businessTitle"].lower())
    ]

    CAP = 25

    return {
        "count": len(matches),
        "returned": min(len(matches), CAP),
        "workers": [
            {
                "name": w["descriptor"],
                "title": w["businessTitle"],
                "department": w["primarySupervisoryOrganization"]["descriptor"],
                "location": w["location"]["descriptor"],
            }
            for w in matches[:CAP]
        ]
    }

def get_team_time_off(manager_name: str, time_off_plan: str, threshold: float | None = None) -> dict:
    manager = get_worker(manager_name)
    if "error" in manager:
        return manager

    if time_off_plan not in ["Vacation", "Sick Leave", "Floating Holiday"]:
        return {"error": f"Invalid time off plan '{time_off_plan}'. Must be one of Vacation, Sick Leave, Floating Holiday."}

    team = {
        w["descriptor"] for w in WORKERS
        if w["manager"] and w["manager"]["descriptor"] == manager["name"]
    }

    rows = [
        {"name": b["worker"]["descriptor"], "balance": b["balance"]}
        for b in TIME_OFF_BALANCES
        if b["worker"]["descriptor"] in team and b["timeOffPlan"] == time_off_plan
    ]

    if threshold is not None:
        rows = [r for r in rows if r["balance"] < threshold]

    rows.sort(key=lambda r: r["balance"])

    return {
        "manager": manager["name"],
        "plan": time_off_plan,
        "unit": "Days",
        "threshold": threshold,
        "team_size": len(team),
        "matched": len(rows),
        "workers": rows,
    }
    

# 2. The Schema -> This text is ALL the model know about the funtion.
GET_WORKER_SCHEMA = {
    "name": "get_worker",
    "description": (    
        "Look up one employee by name and return their job title, department, "
        "location, hire date and manager. Use this whenever the user asks "
        "about a specific person."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Full or partial name of the employee, e.g. 'Carol Bahl'.",
            }
        },
        "required": ["name"],
    },
}

GET_DIRECT_REPORTS_SCHEMA = {
    "name": "get_direct_reports",
    "description": (
        "Look up all direct reports for a given manager by name and return their names and titles. "
        "Use this whenever the user asks about a manager's team."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "manager_name": {
                "type": "string",
                "description": "Full or partial name of the manager, e.g. 'Alice Smith'.",
            }
        },
        "required": ["manager_name"],
    },
}

GET_TIME_OFF_BALANCE_SCHEMA = {
    "name": "get_time_off_balance",
    "description": (
        "Look up the time off balance for a given employee by name and return their balance for each time off plan. "
        "Use this whenever the user asks about an employee's time off balance."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Full or partial name of the employee, e.g. 'John Doe'.",
            }
        },
        "required": ["name"],
    },
}

GET_SEARCH_WORKERS_SCHEMA = {
    "name": "search_workers",
    "description": (
        "Search for workers by department, location, or title and return their names and titles. "
        "Use this whenever the user asks about employees in a specific department, location, or with a specific title."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "department": {
                "type": "string",
                "description": "Full or partial name of the department, e.g. 'Engineering'.",
            },
            "location": {
                "type": "string",
                "description": "Full or partial name of the location, e.g. 'New York'.",
            },
            "title": {
                "type": "string",
                "description": "Full or partial job title, e.g. 'Software Engineer'.",
            }
        },
        "required": [],
    },
}

GET_TEAM_TIME_OFF_SCHEMA = {
    "name": "get_team_time_off",
    "description": (
        "Return the balance of one time-off plan for every direct report of a manager, sorted lowest first. Takes the manager's name directly; no need to look up the team first."
        "Use for any question about a team's time off: who is low, who has the most, or the full list."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "manager_name": {
                "type": "string",
                "description": "Full or partial name of the manager, e.g. 'Alice Smith'.",
            },
            "time_off_plan": {
                "type": "string",
                "enum": ["Vacation", "Sick Leave", "Floating Holiday"],
                "description": "The time off plan to check, e.g. 'Vacation'.",
            },
            "threshold": {
                "type": "number",
                "description": "Optional. If given, return only people with a balance strictly below this many days. Omit to return the whole team.",
            }
        },
        "required": ["manager_name", "time_off_plan"],
    },
}

# 3. The dispatcher (Runner) -> Maps the name the model asks for to the real function.

TOOLS = {
    "get_worker": get_worker, 
    "get_direct_reports": get_direct_reports,
    "get_time_off_balance": get_time_off_balance,
    "search_workers": search_workers,
    "get_team_time_off": get_team_time_off,
    }

def run_tool(name: str, agruments: dict) -> str:
    if name not in TOOLS:
        return json.dumps({"error": f"Unknown tool '{name}'."})
    return json.dumps(TOOLS[name](**agruments), ensure_ascii=False)

if __name__ == "__main__":
    # Pretend to be the model: these are the requests it would send back.
    # print(run_tool("search_workers", {"department": "Finance", "location": "London"}))  # 13, all Finance + London
    # print(run_tool("search_workers", {"department": "Engineering"})[:300])              # total 40, returned 25
    # print(run_tool("search_workers", {"title": "Accountant"})[:300])                    # only Accountants
    # print(run_tool("search_workers", {}))                                               # error, not 200 people

    # result = json.loads(run_tool("search_workers", {"department": "Engineering"}))
    # print(result["count"], len(result["workers"]))

    print(run_tool("get_team_time_off", {"manager_name": "Tom Davis", "time_off_plan": "Vacation", "threshold": 5}))
    print(run_tool("get_team_time_off", {"manager_name": "Tom Davis", "time_off_plan": "Vacation"}))
    print(run_tool("get_team_time_off", {"manager_name": "Carol Bahl", "time_off_plan": "Vacation"}))
    print(run_tool("get_team_time_off", {"manager_name": "Zzyzx", "time_off_plan": "Vacation"}))