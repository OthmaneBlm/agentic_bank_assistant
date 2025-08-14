from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from agentic_bank.agents.base import BaseAgentImpl
from agentic_bank.core.llm.azure import AzureLLM

class FAQState(BaseModel):
    last_query: Optional[str] = None
    fsm: str = "ANSWER"

class FAQAgentLLM(BaseAgentImpl):
    name = "agent-faq-llm"
    def __init__(self, prompts_dir: Path):
        super().__init__(prompts_dir)
        self.llm = AzureLLM()
        self.tools_schema: List[Dict[str, Any]] = [{
            "type":"function",
            "function": {
                "name":"knowledge_retrieve",
                "description":"Retrieve top passages for a user question.",
                "parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}
            }
        }]

    def plan(self, turn, memory: Dict[str, Any]) -> List[Dict[str, Any]]:
        s = FAQState(**memory) if memory else FAQState()
        memory["handled_topic"] = "faq"
        system = "You answer banking FAQs using retrieved passages. Keep it short and grounded."
        from agentic_bank.api.main import tool_exec
        answer, _ = self.llm.chat_with_tools(
            messages=[{"role":"user","content":f"Question: {turn.text or ''}\nFirst, call knowledge_retrieve(query). Then answer briefly."}],
            tools=self.tools_schema,
            system=system,
            tool_executor=tool_exec,
        )
        s.last_query = turn.text or s.last_query
        s.fsm = "DONE"
        memory.update(s.model_dump())
        return [ self.respond(answer or "I don't have that information.") ]