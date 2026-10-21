"""What every backend must provide. Tools only ever talk to this."""
from typing import Protocol, TypedDict


class Worker(TypedDict):
    workerId: str            # Employee ID in the tenant, "100xx" in the mock
    name: str
    title: str
    department: str
    location: str
    managerId: str | None    # None for the CEO


class Balance(TypedDict):
    plan: str                # "Paid Time Off", "Vacation", ... whatever the source calls it
    balance: float
    unit: str                # "Hours" or "Days": never assume


class Pay(TypedDict):
    annualBasePay: float
    currency: str


class PermissionDenied(Exception):
    """The SOURCE refused (e.g. Workday 403). Tools turn this into _deny(...)."""


class Backend(Protocol):
    def current_user_id(self) -> str | None: ...
    def find_workers(self, query: str) -> list[Worker]: ...        # digits = exact workerId, else name match
    def get_worker(self, worker_id: str) -> Worker | None: ...
    def direct_reports(self, worker_id: str) -> list[Worker]: ...
    def search(self, department: str, location: str, title: str) -> list[Worker]: ...
    def time_off_balances(self, worker_id: str) -> list[Balance]: ...
    def time_off_plans(self) -> list[str]: ...
    def compensation(self, worker_id: str) -> Pay | None: ...