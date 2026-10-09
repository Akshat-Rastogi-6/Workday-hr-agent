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


#1. The Funtion -> A simple Python funtion with no AI involved.

def get_worker(name: str) -> dict:
    """Find a worker by full or partial name (case sensitive)."""
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
    """ Find all the workers name and title who reports to a given manager by name (case sensitive)."""
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

# 3. The dispatcher (Runner) -> Maps the name the model asks for to the real function.

TOOLS = {
    "get_worker": get_worker, 
    "get_direct_reports": get_direct_reports
    }

def run_tool(name: str, agruments: dict) -> str:
    if name not in TOOLS:
        return json.dumps({"error": f"Unknown tool '{name}'."})
    return json.dumps(TOOLS[name](**agruments), ensure_ascii=False)

if __name__ == "__main__":
    # Pretend to be the model: these are the requests it would send back.
    print(run_tool("get_worker", {"name": "Carol Bahl"}))
    print(run_tool("get_worker", {"name": "an"}))
    print(run_tool("get_worker", {"name": "Zzyzx"}))
    
    print(run_tool("get_direct_reports", {"manager_name": "Tom Davis"}))
    print(run_tool("get_direct_reports", {"manager_name": "an"}))