"""Pick the backend once, from WORKDAY_BACKEND (default: mock)."""
import os

_backend = None

def get_backend():
    global _backend
    if _backend is None:
        name = os.getenv("WORKDAY_BACKEND", "mock")
        if name == "mock":
            from backends.mock import MockBackend
            _backend = MockBackend()
        elif name == "tenant":
            from backends.workday import WorkdayBackend
            _backend = WorkdayBackend()
        else:
            raise ValueError(f"Unknown WORKDAY_BACKEND '{name}'")
    return _backend