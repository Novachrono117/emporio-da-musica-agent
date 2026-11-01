"""The agent's "today": snapshot date, real time of day, or a fixed moment."""

from datetime import date, datetime, timedelta, timezone

import pytest

from emporio.config import DEFAULT_TODAY, STORE_TZ, agent_now

# 23:30 in Brasília (UTC-3) is 22:30 in Campo Grande (UTC-4).
CLOCK = lambda: datetime(2026, 11, 1, 23, 30, tzinfo=timezone(timedelta(hours=-3)))  # noqa: E731


def test_empty_means_the_snapshot_day_with_the_real_store_time():
    now = agent_now("", clock=CLOCK)
    assert now.date() == DEFAULT_TODAY == date(2026, 3, 23)
    assert (now.hour, now.minute) == (22, 30)
    assert now.utcoffset() == timedelta(hours=-4)


def test_a_date_keeps_the_real_time_of_day():
    now = agent_now("2026-03-28", clock=CLOCK)
    assert (now.date(), now.hour) == (date(2026, 3, 28), 22)


def test_a_full_moment_fixes_date_and_time_in_store_time():
    assert agent_now("2026-03-29T10:15", clock=CLOCK) == datetime(2026, 3, 29, 10, 15, tzinfo=STORE_TZ)
    assert agent_now("2026-03-29T12:00-03:00", clock=CLOCK).hour == 11


def test_the_environment_variable_is_read(monkeypatch):
    monkeypatch.setenv("EMPORIO_TODAY", "2026-04-01")
    assert agent_now(clock=CLOCK).date() == date(2026, 4, 1)


def test_invalid_values_are_rejected():
    with pytest.raises(ValueError, match="EMPORIO_TODAY"):
        agent_now("23/03/2026", clock=CLOCK)
