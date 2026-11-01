"""The policy manual split into numbered sections."""

import pytest

from emporio.data.policy import PAGE_HEADER, _split_sections, load_policy_manual

SECTION_IDS = [
    "0", "1", "1.1", "1.2", "2", "3", "3.1", "4", "4.1", "4.2", "4.3", "4.4", "5", "5.1", "5.2", "5.3",
    "6", "6.1", "6.2", "7", "7.1", "7.2", "7.3", "8", "8.1", "8.2", "8.3", "9", "10",
]  # fmt: skip


@pytest.fixture(scope="module")
def manual():
    return load_policy_manual()


def test_every_numbered_section_is_found_in_order(manual):
    assert [s.id for s in manual.sections] == SECTION_IDS
    assert manual.section("3.1").title == "Regras de Parcelamento"
    assert manual.section("10").title == "Disposições Finais"


def test_page_headers_and_footers_are_dropped(manual):
    for section in manual.sections:
        assert PAGE_HEADER not in section.text
        assert "Página " not in section.text


def test_sections_that_cross_a_page_break_are_whole(manual):
    assert "Jadlog" in manual.section("5.2").text
    assert "recusar o recebimento" in manual.section("5.2").text
    assert "5. Fechamento" in manual.section("7.2").text
    assert "exclusão de seus dados" in manual.section("9").text


def test_key_rules_survive_extraction(manual):
    assert "parcela mínima de R$ 80,00" in manual.section("3.1").text
    assert "R$ 2.000,00" in manual.section("3.1").text
    assert "30 (trinta) dias" in manual.section("4.2").text
    assert "90" in manual.section("8.1").text and "(noventa) dias" in manual.section("8.1").text
    assert "PIX | Pagamento à vista | 5% de desconto" in manual.section("3").text


def test_contradictions_are_kept_as_written(manual):
    # The parser does not fix the manual; the agent's rules do (docs/DATA_NOTES.md).
    assert "contato@emporiodamusica.com.br" in manual.section("0").text
    assert "contato@empóriodamusica.com.br" in manual.section("1.2").text
    assert "(67) 3321-4500" in manual.section("7").text


def test_chapter_returns_the_section_and_its_sub_sections(manual):
    assert [s.id for s in manual.chapter("4")] == ["4", "4.1", "4.2", "4.3", "4.4"]
    assert [s.id for s in manual.chapter("10")] == ["10"]


def test_out_of_order_headings_stay_in_the_text():
    lines = ["Capa", "1. Um", "texto", "3. Pulado", "1.1 Sub", "2. Dois", "  4. Recuado"]
    sections = _split_sections(lines)
    assert [s.id for s in sections] == ["0", "1", "1.1", "2"]
    assert "3. Pulado" in sections[1].text
    assert "4. Recuado" in sections[3].text
