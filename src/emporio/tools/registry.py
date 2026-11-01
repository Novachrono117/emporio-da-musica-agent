"""The tools the agent may call, their definitions for the model and the dispatcher (decision D-006)."""

from __future__ import annotations

from typing import Any

from emporio.tools import catalog, orders, payments, policy_tools, returns, support
from emporio.tools.base import Result, ToolContext, ToolError, validate_arguments

TOOLS = (*catalog.TOOLS, *orders.TOOLS, *payments.TOOLS, *returns.TOOLS, *policy_tools.TOOLS, *support.TOOLS)
_BY_NAME = {tool.name: tool for tool in TOOLS}


def tool_definitions() -> list[dict[str, Any]]:
    """Provider-neutral definitions (name, description, JSON Schema); each LLM adapter translates them."""
    return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in TOOLS]


def run_tool(ctx: ToolContext, name: str, arguments: object) -> Result:
    """Validate the arguments and run the tool. A refused request comes back as {"error": {"code", "message"}}."""
    try:
        tool = _BY_NAME.get(name)
        if tool is None:
            raise ToolError("unknown_tool", f"no tool named {name!r}")
        return tool.handler(ctx, **validate_arguments(tool.input_schema, arguments))
    except ToolError as error:
        return {"error": {"code": error.code, "message": error.message}}
