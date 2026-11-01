"""Command-line chat with the agent: python -m emporio [--provider ...] [--model ...] [--session ID] [--verbose].

Provider and model come from the options, then LLM_PROVIDER and LLM_MODEL in .env, then the defaults in emporio.llm.
Each turn is saved to sessions/<id>.json, so a conversation can be resumed with --session.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from emporio.agent.loop import Agent
from emporio.agent.memory import SessionError, SessionStore, new_session
from emporio.agent.prompts import GREETING
from emporio.agent.usage import UsageLog
from emporio.config import STORE_TZ, agent_now
from emporio.data.memory import InMemoryStore
from emporio.data.policy import load_policy_manual
from emporio.llm import DEFAULT_MODELS, PROVIDERS, create_client, redact
from emporio.llm.base import LLMError, ToolCall
from emporio.tickets import TicketLog
from emporio.tools.base import Result, ToolContext

ROOT = Path(__file__).resolve().parents[2]
EXIT_WORDS = {"sair", "exit", "quit"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m emporio", description="Empório da Música virtual assistant.")
    parser.add_argument("--provider", choices=PROVIDERS, help="default: LLM_PROVIDER in .env, else ollama")
    parser.add_argument("--model", help="default: LLM_MODEL in .env, else the provider's default")
    parser.add_argument("--session", help="resume a saved session by its id")
    parser.add_argument("--verbose", action="store_true", help="show each tool call and its result")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # the Windows console defaults to a legacy code page
    load_dotenv(ROOT / ".env")
    store = SessionStore()
    try:
        session = store.load(args.session) if args.session else None
    except SessionError as error:
        print(error)
        return 2
    provider = args.provider or (session.provider if session else os.getenv("LLM_PROVIDER") or "ollama")
    if provider not in PROVIDERS:
        print(f"Unknown provider {provider!r}; use one of: {', '.join(PROVIDERS)}")
        return 2
    if args.model:
        model = args.model
    elif session and session.provider == provider:
        model = session.model
    elif provider == os.getenv("LLM_PROVIDER") and os.getenv("LLM_MODEL"):
        model = os.environ["LLM_MODEL"]  # LLM_MODEL belongs to LLM_PROVIDER
    else:
        model = DEFAULT_MODELS[provider]
    try:
        llm = create_client(provider, model)
    except LLMError as error:
        print(redact(str(error)))
        return 2

    now = agent_now()
    # Named by the real clock: the store date is simulated (D-005, rule 7), the conversation is not.
    session = session or new_session(provider, model, datetime.now(STORE_TZ))
    ctx = ToolContext(InMemoryStore.from_csv(), load_policy_manual(), TicketLog())
    agent = Agent(llm, ctx, session, UsageLog(), on_tool=_print_tool if args.verbose else None)

    print(f"Empório da Música, assistente virtual ({provider} / {model})")
    print(f"Data da loja: {now:%d/%m/%Y} (EMPORIO_TODAY). Sessão {session.id}. Digite 'sair' para encerrar.")
    if not session.messages:
        print(f"\nAssistente: {GREETING}")  # fixed, outside the history (D-009)
    while True:
        try:
            text = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text.lower() in EXIT_WORDS:
            break
        try:
            answer = agent.reply(text)
        except LLMError as error:
            print(f"\n(O assistente não respondeu: {redact(str(error))}. Tente de novo.)")
            continue
        print(f"\nAssistente: {answer}")
        store.save(session)
    print(f"\nSessão {session.id} salva. Para continuar: python -m emporio --session {session.id}")
    return 0


def _print_tool(call: ToolCall, result: Result) -> None:
    arguments = json.dumps(call.arguments, ensure_ascii=False)
    output = json.dumps(result, ensure_ascii=False)
    print(f"  [tool] {call.name}({arguments}) -> {output[:300]}{'...' if len(output) > 300 else ''}")
