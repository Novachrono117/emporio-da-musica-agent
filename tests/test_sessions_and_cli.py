"""Saved sessions and the command-line chat, with a scripted LLM (decision D-008)."""

import json

import pytest
from conftest import MONDAY_10AM, ScriptedLLM, text, tools

from emporio import cli
from emporio.agent.memory import SessionError, SessionStore, new_session
from emporio.agent.prompts import GREETING
from emporio.agent.usage import UsageLog
from emporio.llm.base import LLMError
from emporio.tickets import TicketLog


def test_session_round_trip(tmp_path):
    store = SessionStore(tmp_path)
    session = new_session("ollama", "qwen", MONDAY_10AM)
    session.messages.append({"role": "user", "content": "Olá, violão até R$ 1.000?"})
    session.failed_order_lookups, session.seen_products = 2, [81, 95]
    store.save(session)
    assert store.load(session.id) == session
    assert "violão" in (tmp_path / f"{session.id}.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("session_id", ["../secrets", "20260323-100000-zzzzzz", ""])
def test_session_ids_cannot_name_other_files(tmp_path, session_id):
    with pytest.raises(SessionError, match="invalid session id"):
        SessionStore(tmp_path).load(session_id)


def test_unknown_session_is_reported(tmp_path):
    with pytest.raises(SessionError, match="no saved session"):
        SessionStore(tmp_path).load("20260323-100000-abcdef")


@pytest.fixture
def chat(tmp_path, monkeypatch, capsys):
    """Run the CLI with scripted input and a scripted LLM; returns (exit code, output, sessions folder)."""
    monkeypatch.setenv("EMPORIO_TODAY", "2026-03-23T10:00")
    monkeypatch.setattr(cli, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "SessionStore", lambda: SessionStore(tmp_path / "sessions"))
    monkeypatch.setattr(cli, "UsageLog", lambda: UsageLog(tmp_path / "usage.jsonl"))
    monkeypatch.setattr(cli, "TicketLog", lambda: TicketLog(tmp_path / "tickets.jsonl"))

    def run(lines, llm, argv=("--provider", "ollama")):
        monkeypatch.setattr(cli, "create_client", lambda provider, model: llm)
        answers = iter(lines)

        def fake_input(prompt=""):
            try:
                return next(answers)
            except StopIteration:
                raise EOFError from None

        monkeypatch.setattr("builtins.input", fake_input)
        code = cli.main(list(argv))
        return code, capsys.readouterr().out, tmp_path / "sessions"

    return run


def test_cli_chats_saves_and_shows_tools_when_verbose(chat):
    llm = ScriptedLLM(tools(("search_products", {"query": "Takamine GD20"})), text("Custa R$ 2.199,00."))
    code, out, sessions = chat(["Quanto custa o Takamine GD20?", "sair"], llm, ("--provider", "ollama", "--verbose"))
    assert code == 0
    assert "Data da loja: 23/03/2026" in out
    assert "[tool] search_products" in out and "Assistente: Custa R$ 2.199,00." in out
    [saved] = sessions.glob("*.json")
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["seen_products"] == [95]
    assert not data["created_at"].startswith("2026-03-23")  # the real clock, not the simulated store date
    assert f"--session {saved.stem}" in out


def test_cli_survives_a_provider_error(chat):
    llm = ScriptedLLM(LLMError("gemini RateLimitError (HTTP 429)"), text("Olá!"))
    code, out, sessions = chat(["oi", "oi de novo"], llm)
    assert code == 0
    assert "O assistente não respondeu: gemini RateLimitError (HTTP 429)" in out
    assert "Assistente: Olá!" in out
    [saved] = sessions.glob("*.json")
    assert [m["content"] for m in json.loads(saved.read_text(encoding="utf-8"))["messages"]] == ["oi de novo", "Olá!"]


def test_cli_resumes_a_session(chat):
    _, first_out, sessions = chat(["oi"], ScriptedLLM(text("Olá!")))
    assert f"Assistente: {GREETING}" in first_out
    [saved] = sessions.glob("*.json")
    llm = ScriptedLLM(text("Claro."))
    code, out, _ = chat(["e agora?"], llm, ("--session", saved.stem))
    assert code == 0 and "Assistente: Claro." in out
    assert GREETING not in out  # greeted once, in the first session
    # The greeting is printed, never sent to the model as history.
    assert [m["content"] for m in llm.calls[0]["messages"]] == ["oi", "Olá!", "e agora?"]


def test_without_options_the_cli_uses_the_model_the_evaluation_chose(chat, monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    code, out, _ = chat(["sair"], ScriptedLLM(), ())
    assert code == 0 and "(gemini / gemini-3.5-flash-lite)" in out


def test_cli_reports_a_missing_key_without_starting(chat, monkeypatch):
    def no_key(provider, model):
        raise LLMError("GEMINI_API_KEY is not set: add it to .env (see .env.example)")

    monkeypatch.setattr(cli, "create_client", no_key)
    assert cli.main(["--provider", "gemini"]) == 2
