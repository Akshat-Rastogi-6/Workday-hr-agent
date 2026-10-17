"Loads the data from Mock teant. Everything else import here."

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def _load(name):
    return json.loads((HERE / "data" / f"{name}.json").read_text(encoding="utf-8"))["data"]

WORKERS = _load("workers")
TIME_OFF_BALANCES = _load("time_off_balances")
COMPENSATION = _load("compensation")
WORKERS_BY_ID = {w["id"]: w for w in WORKERS}