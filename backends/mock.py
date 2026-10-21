"""Mock backend: answers data questions from the JSON files. No permissions, no model-facing text."""
import json
from pathlib import Path

from backends.base import Worker, Balance, Pay

DATA = Path(__file__).resolve().parent.parent / "data"

def _load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))["data"]


class MockBackend:
    def __init__(self):
        self._workers = _load("workers")
        self._balances = _load("time_off_balances")
        self._comp = _load("compensation")
        self._by_internal = {w["id"]: w for w in self._workers}       # 32-hex id -> raw record
        self._by_wid = {w["workerId"]: w for w in self._workers}      # "10006"  -> raw record

    # ---- the ONE place raw records become the shared shape
    def _to_worker(self, w: dict) -> Worker:
        mgr = w["manager"]
        return {
            "workerId": w["workerId"],
            "name": w["descriptor"],
            "title": w["businessTitle"],
            "department": w["primarySupervisoryOrganization"]["descriptor"],
            "location": w["location"]["descriptor"],
            "managerId": self._by_internal[mgr["id"]]["workerId"] if mgr else None,
        }

    # ---- interface
    def current_user_id(self) -> str | None:
        return None        # the mock has no login; identity comes from WORKDAY_USER (see below)

    def get_worker(self, worker_id: str) -> Worker | None:
        w = self._by_wid.get(str(worker_id))
        return self._to_worker(w) if w else None

    def find_workers(self, query: str) -> list[Worker]:
        q = str(query).strip()
        if q.isdigit():
            w = self._by_wid.get(q)
            return [self._to_worker(w)] if w else []
        return [self._to_worker(w) for w in self._workers if q.lower() in w["descriptor"].lower()]

    def direct_reports(self, worker_id: str) -> list[Worker]:
        mgr = self._by_wid.get(str(worker_id))
        if not mgr:
            return []
        return [self._to_worker(w) for w in self._workers
                if w["manager"] and w["manager"]["id"] == mgr["id"]]

    def search(self, department: str, location: str, title: str) -> list[Worker]:
        return [self._to_worker(w) for w in self._workers
                if (not department or department.lower() in w["primarySupervisoryOrganization"]["descriptor"].lower())
                and (not location or location.lower() in w["location"]["descriptor"].lower())
                and (not title or title.lower() in w["businessTitle"].lower())]

    def time_off_balances(self, worker_id: str) -> list[Balance]:
        w = self._by_wid.get(str(worker_id))
        if not w:
            return []
        return [{"plan": b["timeOffPlan"], "balance": b["balance"], "unit": b["unit"]}
                for b in self._balances if b["worker"]["id"] == w["id"]]

    def time_off_plans(self) -> list[str]:
        return sorted({b["timeOffPlan"] for b in self._balances})

    def compensation(self, worker_id: str) -> Pay | None:
        w = self._by_wid.get(str(worker_id))
        if not w:
            return None
        c = next((c for c in self._comp if c["worker"]["id"] == w["id"]), None)
        if c is None:
            return None
        return {"annualBasePay": float(c["annualBasePay"]), "currency": c["currency"]}

if __name__ == "__main__":
    b = MockBackend()
    print(b.get_worker("10006"))                   # Stephanie, managerId 10003
    print([w["name"] for w in b.find_workers("Andy")])   # Andy Nair + Randy Weinhage
    print(len(b.direct_reports("10003")))          # 18
    print(b.time_off_balances("10006"))            # 3 plans, unit Days
    print(b.compensation("10006"))                 # 85100.0 GBP
    print(b.compensation("99999"))                 # None
    print(len(b.search("Engineering", "", "")))    # 40