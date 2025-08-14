from typing import Callable, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from agentic_bank.core.logging import get_logger
_log = get_logger("tools")

@dataclass
class Tool:
    tool_id: str
    handler: Callable[[Dict[str, Any]], Dict[str, Any]]
    description: str = ""

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.tool_id] = tool

    def get(self, tool_id: str) -> Optional[Tool]:
        return self._tools.get(tool_id)

class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def call(self, tool_id: str, args: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        _log.debug(f"call -> {tool_id}", extra={"stage":"tool.call", "tool":tool_id})
        tool = self.registry.get(tool_id)
        if not tool:
            _log.error("tool not found", extra={"stage":"tool.error", "tool":tool_id})
            return ("error", {"message":"tool_not_found", "tool_id": tool_id})
        try:
            data = tool.handler(args)
            _log.debug(f"ok <- {tool_id}", extra={"stage":"tool.ok", "tool":tool_id, "status":"ok"})
            return ("ok", data)
        except Exception as e:
            _log.exception(f"tool error {tool_id}: {e}", extra={"stage":"tool.error", "tool":tool_id, "status":"error"})
            return ("error", {"message": str(e)})