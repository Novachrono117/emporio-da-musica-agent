"""get_store_policy: sections per topic, notes where the business rules resolve a conflict (D-005; D-006)."""

import json

import pytest

from emporio.tools.policy_tools import TOPICS, get_store_policy


@pytest.mark.parametrize("topic", [t for t in TOPICS if t != "contact"])
def test_every_topic_returns_its_sections_with_text(ctx, topic):
    result = get_store_policy(ctx, topic)
    assert [s["id"] for s in result["sections"]] == list(TOPICS[topic])
    assert all(s["title"] and s["text"] for s in result["sections"])


def test_payment_notes_say_that_3_1_wins(ctx):
    result = get_store_policy(ctx, "payment")
    assert "Parcela mínima de R$ 100,00" in result["sections"][0]["text"]  # the table, kept as written
    assert any("3.1 overrides" in note and "R$ 80,00" in note for note in result["notes"])


def test_defect_notes_never_send_the_customer_to_the_manufacturer(ctx):
    for topic in ("returns_exchanges", "warranty"):
        notes = " ".join(get_store_policy(ctx, topic)["notes"])
        assert "never send the customer to the manufacturer" in notes
        assert "CDC, art. 18" in notes


def test_regret_note_limits_it_to_purchases_outside_the_store(ctx):
    notes = " ".join(get_store_policy(ctx, "returns_exchanges")["notes"])
    assert "outside the store" in notes and "CDC, art. 49" in notes


def test_contact_comes_from_the_resolved_data_not_the_manual(ctx):
    result = get_store_policy(ctx, "contact")
    assert result["sections"] == []
    assert result["contacts"] == {
        "whatsapp": "(67) 3321-4500",
        "phone": "(67) 3341-4444",
        "email": "contato@emporiodamusica.com.br",
    }
    assert "empóriodamusica" not in json.dumps(result, ensure_ascii=False)
    assert result["company"]["cnpj"] == "12.345.678/0001-90"


def test_hours_say_whether_the_store_is_open(ctx):
    result = get_store_policy(ctx, "hours")  # Monday 10:00
    assert (result["open_now"], result["closes_at"]) == (True, "18:00")
    assert "sábado" in result["hours"]


def test_notes_never_cite_the_internal_decision_log(ctx):
    for topic in TOPICS:
        assert "D-00" not in json.dumps(get_store_policy(ctx, topic))
