"""Company data match the manual (D-005, rule 3) and the store hours are computed in store time."""

from datetime import datetime

import pytest

from emporio.company import COMPANY, CONTACTS, next_opening, store_status
from emporio.config import STORE_TZ


def test_contacts_and_company_data_come_from_the_manual(manual):
    cover, company_table, whatsapp = manual.section("0").text, manual.section("1.2").text, manual.section("7").text
    assert CONTACTS["email"] in cover  # the unaccented form, from the cover
    assert CONTACTS["phone"] in cover and CONTACTS["phone"] in company_table
    assert CONTACTS["whatsapp"] in whatsapp
    assert COMPANY["legal_name"] in company_table and COMPANY["cnpj"] in company_table
    assert "Rua 14 de Maio, 3200" in company_table and "79202-333" in company_table


def test_hours_match_section_2(manual):
    hours = manual.section("2").text
    assert "Segunda a Sexta-feira | 09:00 às 18:00" in hours
    assert "Sábado | 09:00 às 13:00" in hours
    assert "Domingo e Feriados | Fechado" in hours


def _at(day, hour, minute=0):
    return datetime(2026, 3, day, hour, minute, tzinfo=STORE_TZ)  # 23/03/2026 is a Monday


@pytest.mark.parametrize(
    "moment, open_now",
    [
        (_at(23, 9), True),
        (_at(23, 17, 59), True),
        (_at(23, 18), False),
        (_at(23, 8, 59), False),
        (_at(28, 12, 30), True),  # Saturday
        (_at(28, 13), False),
        (_at(29, 10), False),  # Sunday
    ],
)
def test_open_now(moment, open_now):
    assert store_status(moment)["open_now"] is open_now


def test_next_opening():
    assert next_opening(_at(23, 8)) == _at(23, 9)  # later the same morning
    assert next_opening(_at(27, 19)) == _at(28, 9)  # Friday night to Saturday
    assert next_opening(_at(28, 14)) == _at(30, 9)  # Saturday afternoon to Monday
    status = store_status(_at(29, 10))
    assert status["next_opening"] == "segunda-feira, 30/03/2026, às 09:00"
    assert "holidays" in status["holidays_note"].lower()


def test_open_store_says_when_it_closes():
    assert store_status(_at(28, 10)) == {"open_now": True, "closes_at": "13:00"}
