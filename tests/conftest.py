"""Shared fixtures: the real store data, the policy manual and a tool context at a fixed store time."""

from datetime import datetime

import pytest

from emporio.config import STORE_TZ
from emporio.data.memory import InMemoryStore
from emporio.data.policy import load_policy_manual
from emporio.tickets import TicketLog
from emporio.tools.base import ToolContext

# Monday, the default "today" (D-005, rule 7), during business hours.
MONDAY_10AM = datetime(2026, 3, 23, 10, 0, tzinfo=STORE_TZ)


@pytest.fixture(scope="session")
def store():
    return InMemoryStore.from_csv()


@pytest.fixture(scope="session")
def manual():
    return load_policy_manual()


@pytest.fixture
def ctx(store, manual, tmp_path):
    return ToolContext(store, manual, TicketLog(tmp_path / "tickets.jsonl"), now=lambda: MONDAY_10AM)
