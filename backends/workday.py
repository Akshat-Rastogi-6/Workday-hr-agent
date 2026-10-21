"""Workday tenant backend. Translates Workday REST/RaaS responses into the shared shapes.
Read-only by construction: the HTTP client refuses anything but GET."""
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from backends.base import Worker, Balance, Pay, PermissionDenied

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class _Client:
    def __init__(self):
        rest = os.environ["WD_REST_URL"].rstrip("/")
        self._base = rest.split("/ccx/api/")[0] + "/ccx/api"
        self._tenant = rest.split("/")[-1]
        self._token, self._expires = None, 0.0

    def url(self, service: str, path: str) -> str:
        return f"{self._base}/{service}/{self._tenant}/{path.lstrip('/')}"

    def _access_token(self) -> str:
        if self._token and time.time() < self._expires - 60:      # reuse until 1 min before expiry
            return self._token
        r = requests.post(
            os.environ["WD_TOKEN_URL"],
            data={"grant_type": "refresh_token", "refresh_token": os.environ["WD_REFRESH_TOKEN"]},
            auth=(os.environ["WD_CLIENT_ID"], os.environ["WD_CLIENT_SECRET"]),
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._expires = time.time() + float(body.get("expires_in", 900))
        return self._token

    def get(self, url: str, method: str = "GET", **params) -> dict | None:
        if method != "GET":
            raise RuntimeError(f"Refusing {method}: this backend is read-only.")
        r = requests.get(url, params=params,
                         headers={"Authorization": f"Bearer {self._access_token()}"}, timeout=30)
        if r.status_code == 403:
            raise PermissionDenied(r.text[:200])
        if r.status_code == 404:
            return None
        if r.status_code == 500 and "not authorized" in r.text.lower():
            raise PermissionDenied(r.text[:200])
        if not r.ok:
            raise RuntimeError(f"Workday {r.status_code}: {r.text[:200]}")
        return r.json()
    
    def get_all(self, url: str, **params) -> list[dict]:
        """Follow limit/offset paging until 'total' is reached."""
        out, offset = [], 0
        while True:
            body = self.get(url, limit=100, offset=offset, **params) or {}
            page = body.get("data", [])
            out += page
            offset += len(page)
            if not page or offset >= body.get("total", 0):
                return out


class WorkdayBackend:
    def __init__(self):
        self._c = _Client()
        self._emp_id = {}        # WID -> Employee ID cache (WIDs never change)

    # ---- WID <-> Employee ID: the only place WIDs exist
    def _employee_id(self, wid: str) -> str | None:
        if wid not in self._emp_id:
            body = self._c.get(self._c.url("staffing/v6", f"workers/{wid}"))
            self._emp_id[wid] = body.get("workerId") if body else None
        return self._emp_id[wid]

    def _manager_id(self, wid: str, org_id: str) -> str | None:
        org = self._c.get(self._c.url("common/v1", f"supervisoryOrganizations/{org_id}"))
        mgr = (org or {}).get("manager")
        if not mgr or mgr["id"] == wid:          # top of the tree (e.g. CEO manages their own org)
            return None
        return self._employee_id(mgr["id"])

    def _to_worker(self, raw: dict, employee_id: str | None = None) -> Worker:
        wid = raw["id"]
        org = raw.get("primarySupervisoryOrganization") or {}
        return {
            "workerId": employee_id or self._employee_id(wid),
            "name": raw["descriptor"],
            "title": raw.get("businessTitle", ""),
            "department": org.get("descriptor", ""),
            "location": (raw.get("location") or {}).get("descriptor", ""),
            "managerId": self._manager_id(wid, org["id"]) if org.get("id") else None,
        }

    # ---- interface (part 1)
    def current_user_id(self) -> str | None:
        me = self._c.get(self._c.url("common/v1", "workers/me"))
        return self._employee_id(me["id"]) if me else None

    def get_worker(self, worker_id: str) -> Worker | None:
        raw = self._c.get(self._c.url("common/v1", f"workers/Employee_ID={worker_id}"))
        return self._to_worker(raw, employee_id=str(worker_id)) if raw else None

    def find_workers(self, query: str) -> list[Worker]:
        q = str(query).strip()
        if q.isdigit():
            w = self.get_worker(q)
            return [w] if w else []
        body = self._c.get(self._c.url("common/v1", "workers"), search=q, limit=100) or {}
        # The list view lacks location, so fetch each match's full record.
        return [self.get_worker(self._employee_id(r["id"])) for r in body.get("data", [])]

    def direct_reports(self, worker_id: str) -> list[Worker]:
        # 403 here is Workday's security domain (Reports: Manager / My Team). Let PermissionDenied propagate.
        raw = self._c.get_all(self._c.url("common/v1", f"workers/Employee_ID={worker_id}/directReports"))
        return [self.get_worker(self._employee_id(r["id"])) for r in raw]

    def search(self, department: str, location: str, title: str) -> list[Worker]:
        # Directory data, public to every signed-in user, so paging through everyone is acceptable here.
        raw = self._c.get_all(self._c.url("common/v1", "workers"))
        dep, ttl = department.lower(), title.lower()
        cheap = [r for r in raw
                 if (not dep or dep in (r.get("primarySupervisoryOrganization") or {}).get("descriptor", "").lower())
                 and (not ttl or ttl in r.get("businessTitle", "").lower())]
        workers = [self.get_worker(self._employee_id(r["id"])) for r in cheap]   # location needs the full record
        return [w for w in workers if w and (not location or location.lower() in w["location"].lower())]

    def time_off_balances(self, worker_id: str) -> list[Balance]:
        raw = self._c.get_all(self._c.url("absenceManagement/v4", "balances"), worker=f"Employee_ID={worker_id}")
        return [{"plan": b["absencePlan"]["descriptor"],
                 "balance": float(b["quantity"]),
                 "unit": b["unit"]["descriptor"]}
                for b in raw]

    def time_off_plans(self) -> list[str]:
        # No "list all plans" endpoint found yet: use the signed-in user's plans.
        me = self.current_user_id()
        return sorted({b["plan"] for b in self.time_off_balances(me)}) if me else []

    def compensation(self, worker_id: str) -> Pay | None:
        body = self._c.get(os.environ["WD_RAAS_COMP_URL"], Employee_ID=str(worker_id), format="json") or {}
        rows = body.get("Report_Entry", [])
        if not rows:
            return None                                         # no such worker / no record
        amount = rows[0].get("Total_Base_Pay_Annualized_-_Amount")
        if amount in (None, ""):
            raise PermissionDenied("pay not visible")           # field security hid it; never report 0
        return {"annualBasePay": float(amount),
                "currency": rows[0].get("Total_Base_Pay_Annualized_-_Currency", "")}


if __name__ == "__main__":
    b = WorkdayBackend()
    print("plans:      ", b.time_off_plans())                          # ['Floating Holiday', 'Paid Time Off'] or similar
    print("Aidan time: ", b.time_off_balances("21142"))                # PTO 150.0 Hours, FH 16.0 Hours
    print("Aidan pay:  ", b.compensation("21142"))                     # expected: annual base pay + currency
    print("no pay:     ", b.compensation("99999"))                     # None
    print("my team:    ", [w["name"] for w in b.direct_reports("21001")])
    try:
        b.direct_reports("21044")                                     # Astor's team, not Logan's
        print("Astor team:  FAIL, should have been denied")
    except PermissionDenied:
        print("Astor team:  denied (correct)")
    print("R&D-P1:     ", [w["name"] for w in b.search("R&D - Product 1", "", "")])   # Aidan, Evelyn
    print("in NY:      ", len(b.search("", "New York", "")))