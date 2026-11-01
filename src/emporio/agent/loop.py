"""The tool-calling loop (PLAN, section 8; decision D-008).

For each customer message: call the model, run the tools it asks for, send the results back, and repeat until it
answers in text. Up to 6 rounds of tools run per message; a seventh request is dropped and the customer gets a fixed
answer that offers a person, without another model call. A refusal or an empty answer gets the same message. Tool
errors go back to the model as data. If the provider fails, the customer's message is taken out of the history, so
the session stays valid, and the error goes up to the caller.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

from emporio.agent.memory import Session
from emporio.agent.prompts import system_prompt
from emporio.agent.usage import UsageLog
from emporio.company import CONTACTS
from emporio.llm.base import LLMClient, LLMError, LLMResponse, Message, ToolCall
from emporio.tools.base import Result, ToolContext
from emporio.tools.registry import run_tool, tool_definitions

MAX_TOOL_ROUNDS = 6
FALLBACK_ANSWER = (
    "Desculpe, não consegui concluir esse atendimento por aqui. Uma pessoa da nossa equipe pode te ajudar: "
    f"WhatsApp {CONTACTS['whatsapp']}, telefone {CONTACTS['phone']} ou e-mail {CONTACTS['email']}."
)
TOOL_FAILED = {"error": {"code": "internal_error", "message": "The tool failed. Apologise and offer a person."}}
BAD_ARGUMENTS = {"error": {"code": "invalid_input", "message": "arguments must be a JSON object"}}

logger = logging.getLogger(__name__)


class Agent:
    def __init__(
        self,
        llm: LLMClient,
        ctx: ToolContext,
        session: Session,
        usage: UsageLog | None = None,
        on_tool: Callable[[ToolCall, Result], None] | None = None,
    ) -> None:
        self.llm = llm
        self.ctx = ctx
        self.session = session
        self.usage = usage
        self.on_tool = on_tool
        ctx.failed_order_lookups = session.failed_order_lookups
        ctx.seen_products = set(session.seen_products)

    def reply(self, text: str) -> str:
        messages = self.session.messages
        start = len(messages)
        messages.append({"role": "user", "content": text})
        try:
            return self._answer(messages)
        except LLMError:
            del messages[start:]
            raise
        finally:
            self.session.failed_order_lookups = self.ctx.failed_order_lookups
            self.session.seen_products = sorted(self.ctx.seen_products)

    def _answer(self, messages: list[Message]) -> str:
        tools = tool_definitions()
        for round_number in range(MAX_TOOL_ROUNDS + 1):
            response = self._complete(messages, tools)
            if response.stop_reason == "refusal" or not (response.tool_calls or response.text.strip()):
                return self._fallback(messages)
            if not response.tool_calls:
                messages.append(response.as_message(self.llm.provider))
                return response.text
            if round_number == MAX_TOOL_ROUNDS:
                return self._fallback(messages)  # the seventh round is dropped: no call is left without a result
            messages.append(response.as_message(self.llm.provider))
            for call in response.tool_calls:
                result = self._run(call)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        raise AssertionError("unreachable")

    def _complete(self, messages: list[Message], tools: list[dict]) -> LLMResponse:
        started = time.perf_counter()
        response = self.llm.complete(system_prompt(self.ctx.today()), messages, tools)
        if self.usage:
            self.usage.record(
                self.session.id, self.llm.provider, self.llm.model, response, time.perf_counter() - started
            )
        return response

    def _run(self, call: ToolCall) -> Result:
        if call.arguments is None:
            result = BAD_ARGUMENTS
        else:
            try:
                result = run_tool(self.ctx, call.name, call.arguments)
            except Exception:  # a bug in a tool must not end the conversation
                logger.exception("tool %s failed", call.name)
                result = TOOL_FAILED
        if self.on_tool:
            self.on_tool(call, result)
        return result

    def _fallback(self, messages: list[Message]) -> str:
        messages.append({"role": "assistant", "content": FALLBACK_ANSWER, "provider": self.llm.provider, "raw": None})
        return FALLBACK_ANSWER
