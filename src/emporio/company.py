"""Company data, contacts and business hours, as D-005 (rule 3) resolves them from the manual.

The manual gives two e-mails and two WhatsApp numbers; these are the ones D-005 chose. Hours come from section 2;
holidays are not computed (D-005, rule 7). tests/test_company.py checks every value against the manual's text.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

COMPANY = {
    "legal_name": "Empório da Música Instrumentos Musicais Ltda.",
    "trade_name": "Empório da Música",
    "cnpj": "12.345.678/0001-90",
    "address": "Rua 14 de Maio, 3200, Centro, Campo Grande - MS, CEP 79202-333",
}
CONTACTS = {
    "whatsapp": "(67) 3321-4500",
    "phone": "(67) 3341-4444",
    "email": "contato@emporiodamusica.com.br",
}
# Monday is 0, as in datetime.weekday(); Sunday is closed.
OPENING_HOURS = {day: (time(9), time(18)) for day in range(5)} | {5: (time(9), time(13))}
HOURS_TEXT = "Segunda a sexta, das 9h às 18h; sábado, das 9h às 13h; domingo e feriados, fechado."
WEEKDAYS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def store_status(moment: datetime) -> dict[str, object]:
    """Whether the store is open at `moment` (store time) and, if not, when it opens next."""
    hours = OPENING_HOURS.get(moment.weekday())
    if hours and hours[0] <= moment.time() < hours[1]:
        return {"open_now": True, "closes_at": hours[1].strftime("%H:%M")}
    opening = next_opening(moment)
    return {
        "open_now": False,
        "next_opening": f"{WEEKDAYS[opening.weekday()]}, {opening:%d/%m/%Y}, às {opening:%H:%M}",
        "holidays_note": "Holidays are not in this calendar; the store is also closed on holidays (2).",
    }


def next_opening(moment: datetime) -> datetime:
    """The first opening time after `moment`: later the same day, or on the next open day."""
    for offset in range(8):
        day = moment.date() + timedelta(days=offset)
        hours = OPENING_HOURS.get(day.weekday())
        if hours:
            opening = datetime.combine(day, hours[0], tzinfo=moment.tzinfo)
            if opening > moment:
                return opening
    raise AssertionError("OPENING_HOURS has no open day")
