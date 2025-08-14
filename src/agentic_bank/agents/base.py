from typing import List, Dict, Any, Protocol
from pathlib import Path
from agentic_bank.core.messages import TurnInput, TurnOutcome, ToolCall
from agentic_bank.core.tooling import ToolExecutor
from agentic_bank.core.promptkit import PromptBuilder

class AgentBase(Protocol):
    name: str
    prompts: PromptBuilder
    def plan(self, turn: TurnInput, memory: Dict[str, Any]) -> List[Dict[str, Any]]: ...
    def run(self, turn: TurnInput, memory: Dict[str, Any], tools: ToolExecutor) -> TurnOutcome: ...

class BaseAgentImpl:
    name: str = "agent-base"
    def __init__(self, prompts_dir: Path):
        self.prompts = PromptBuilder(prompts_dir)

    def think(self, note: str) -> Dict[str, Any]:
        return {"type":"think", "note": note}
    def call_tool(self, tool_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"type":"tool", "toolId": tool_id, "args": args}
    def respond(self, text: str) -> Dict[str, Any]:
        return {"type":"respond", "text": text}

    def run(self, turn: TurnInput, memory: Dict[str, Any], tools: ToolExecutor) -> TurnOutcome:
        steps = self.plan(turn, memory)
        tool_calls: List[ToolCall] = []
        reply_chunks: List[str] = []

        for step in steps:
            if step["type"] == "tool":
                status, data = tools.call(step["toolId"], step["args"])
                tool_calls.append(ToolCall(toolId=step["toolId"], arguments=step["args"]))
                memory[f"tool:{step['toolId']}"] = {"status": status, "data": data}
            if step["type"] == "respond":
                reply_chunks.append(step["text"])

        reply = " ".join(reply_chunks) if reply_chunks else "Done."

        # Infer terminal & topic from memory/state if present
        fsm_state = memory.get("fsm")
        is_terminal = bool(fsm_state in {"DONE", "ESCALATE"})
        handled_topic = memory.get("handled_topic")  # agents can set this; or set here by name

        # Default topic by agent name if not set
        if not handled_topic:
            if self.name.startswith("agent-card"):
                handled_topic = "card_block"
            elif self.name.startswith("agent-appointment"):
                handled_topic = "appointment_booking"
            elif self.name.startswith("agent-faq"):
                handled_topic = "faq"

        return TurnOutcome(
            replyText=reply,
            toolCalls=tool_calls,
            fsmState=fsm_state,
            isTerminal=is_terminal,
            handledTopic=handled_topic
        )
