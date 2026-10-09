"""
Generate synthetic, Workday-shaped HR data for the mock API.

Everything here is fake. Names come from Faker, and the field names loosely
follow Workday's public REST API (id / descriptor pairs, nested references).
Check the shapes against the public REST directory before you rely on them.

Run:  pip install faker && python generate_data.py
Output: data/workers.json, data/organizations.json,
        data/time_off_balances.json, data/compensation.json
"""

import json
import random
import uuid
from datetime import date
from pathlib import Path

from faker import Faker

SEED = 42          # same seed -> same data every run
NUM_WORKERS = 200
OUT_DIR = Path("data")

random.seed(SEED)
fake = Faker(["en_US", "en_GB", "de_DE", "en_IN"])
Faker.seed(SEED)

# ---------------------------------------------------------------- reference data
LOCATIONS = [
    {"name": "Berlin", "country": "Germany", "currency": "EUR"},
    {"name": "London", "country": "United Kingdom", "currency": "GBP"},
    {"name": "Bengaluru", "country": "India", "currency": "INR"},
    {"name": "Austin", "country": "United States of America", "currency": "USD"},
]

# department -> (job titles for individual contributors, annual pay range in EUR)
DEPARTMENTS = {
    "Engineering": (["Software Engineer", "Senior Software Engineer", "QA Engineer"], (55000, 110000)),
    "Sales": (["Account Executive", "Sales Development Rep"], (40000, 90000)),
    "Finance": (["Financial Analyst", "Accountant"], (45000, 85000)),
    "Human Resources": (["HR Partner", "Recruiter"], (42000, 80000)),
    "Customer Support": (["Support Specialist", "Support Engineer"], (35000, 65000)),
}

# rough conversion so pay looks plausible per location
CURRENCY_FACTOR = {"EUR": 1.0, "GBP": 0.85, "USD": 1.1, "INR": 30.0}

TIME_OFF_PLANS = [("Vacation", 25), ("Sick Leave", 10), ("Floating Holiday", 2)]


def new_id() -> str:
    """Workday IDs are 32-char hex strings; uuid4().hex has the same look."""
    return uuid.UUID(int=random.getrandbits(128)).hex


def ref(obj: dict) -> dict:
    """Workday references other objects as {id, descriptor}."""
    return {"id": obj["id"], "descriptor": obj["descriptor"]}


# ---------------------------------------------------------------- build orgs
locations = [{"id": new_id(), "descriptor": loc["name"], **loc} for loc in LOCATIONS]

organizations = []
company = {"id": new_id(), "descriptor": "Northwind Global (CEO)", "type": "Supervisory", "superior": None}
organizations.append(company)

dept_orgs = {}
for dept in DEPARTMENTS:
    org = {"id": new_id(), "descriptor": dept, "type": "Supervisory", "superior": ref(company)}
    organizations.append(org)
    dept_orgs[dept] = org


# ---------------------------------------------------------------- build workers
workers, compensation, balances = [], [], []
employee_counter = 10000


def make_worker(title: str, org: dict, manager: dict | None, is_manager: bool, pay_range: tuple) -> dict:
    global employee_counter
    employee_counter += 1
    location = random.choice(locations)
    first, last = fake.first_name(), fake.last_name()
    hire = fake.date_between(start_date=date(2015, 1, 1), end_date=date(2026, 9, 1))

    worker = {
        "id": new_id(),
        "descriptor": f"{first} {last}",
        "workerId": str(employee_counter),
        "primaryWorkEmail": f"{first}.{last}@northwind.example".lower().replace(" ", ""),
        "businessTitle": title,
        "isManager": is_manager,
        "hireDate": hire.isoformat(),
        "workerType": random.choices(["Employee", "Contingent Worker"], weights=[9, 1])[0],
        "primarySupervisoryOrganization": ref(org),
        "location": {"id": location["id"], "descriptor": location["descriptor"], "country": location["country"]},
        "manager": ref(manager) if manager else None,
    }
    workers.append(worker)

    # Sensitive data lives in its own file so the mock API can gate it by role.
    amount = random.randint(*pay_range) * CURRENCY_FACTOR[location["currency"]]
    compensation.append({
        "worker": ref(worker),
        "annualBasePay": round(amount, -2),
        "currency": location["currency"],
        "nationalId": fake.bothify("??######").upper(),   # fake, exists to test masking
    })

    for plan, allowance in TIME_OFF_PLANS:
        balances.append({
            "worker": ref(worker),
            "timeOffPlan": plan,
            "unit": "Days",
            "balance": round(random.uniform(0, allowance), 1),
        })
    return worker


# CEO -> one head per department -> a few team managers -> individual contributors
ceo = make_worker("Chief Executive Officer", company, None, True, (200000, 260000))

remaining = NUM_WORKERS - 1
per_dept, extra = divmod(remaining, len(DEPARTMENTS))

for i, (dept, (titles, pay_range)) in enumerate(DEPARTMENTS.items()):
    dept_size = per_dept + (1 if i < extra else 0)   # spread the remainder
    org = dept_orgs[dept]
    head = make_worker(f"VP, {dept}", org, ceo, True, (130000, 180000))
    org["manager"] = ref(head)

    managers = [
        make_worker(f"{dept} Manager", org, head, True, (pay_range[1], pay_range[1] + 30000))
        for _ in range(3)
    ]
    for _ in range(dept_size - 1 - len(managers)):
        make_worker(random.choice(titles), org, random.choice(managers), False, pay_range)

company["manager"] = ref(ceo)

# ---------------------------------------------------------------- write files
OUT_DIR.mkdir(exist_ok=True)
for name, rows in [
    ("workers", workers),
    ("organizations", organizations),
    ("time_off_balances", balances),
    ("compensation", compensation),
]:
    path = OUT_DIR / f"{name}.json"
    path.write_text(json.dumps({"total": len(rows), "data": rows}, indent=2, ensure_ascii=False))
    print(f"{path}: {len(rows)} records")