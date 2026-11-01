"""Settings read from the environment (.env). API keys are read by the LLM clients, never here."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

# Campo Grande (MS) is on UTC-4 all year (Brazil dropped daylight saving time in 2019); the store hours are local.
STORE_TZ = timezone(timedelta(hours=-4), "Campo Grande (UTC-4)")
# The day after the last order in data/, so order statuses read as current (see docs/DATA_NOTES.md).
DEFAULT_TODAY = date(2026, 3, 23)


def agent_now(value: str | None = None, clock: Callable[[], datetime] | None = None) -> datetime:
    """The agent's current date and time, in store time.

    `value` defaults to EMPORIO_TODAY. A date (YYYY-MM-DD) sets the day and keeps the real time of day; a full ISO
    date and time (YYYY-MM-DDTHH:MM) fixes both, which tests and the evaluation use. Empty means DEFAULT_TODAY.
    """
    raw = (os.getenv("EMPORIO_TODAY", "") if value is None else value).strip()
    real_now = (clock or (lambda: datetime.now(STORE_TZ)))().astimezone(STORE_TZ)
    try:
        if not raw:
            return datetime.combine(DEFAULT_TODAY, real_now.timetz())
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return datetime.combine(date.fromisoformat(raw), real_now.timetz())
        moment = datetime.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"EMPORIO_TODAY must be YYYY-MM-DD or YYYY-MM-DDTHH:MM, got {raw!r}") from None
    return moment.replace(tzinfo=STORE_TZ) if moment.tzinfo is None else moment.astimezone(STORE_TZ)
