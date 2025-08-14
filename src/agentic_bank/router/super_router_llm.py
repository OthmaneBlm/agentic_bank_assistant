from __future__ import annotations
from typing import Dict, Any, Optional, Tuple, List
import json
from agentic_bank.core.llm.azure import AzureLLM
from agentic_bank.core.logging import get_logger

log = get_logger("router.super")

SYSTEM = (
  "Banking super-router. Decide to CONTINUE with current agent, HANDOFF to another, or CLARIFY.\n"
  "Rules:\n"
  "- If the user's new message is acknowledgement/thanks or closure, do NOT ask follow-ups.\n"
  "- If clearly different capability than active topic, HANDOFF to the best agent.\n"
  "- If on-topic, CONTINUE with current agent.\n"
  "- If unclear, CLARIFY with one short question.\n"
  "Return STRICT JSON: {\"decision\":\"continue|handoff|clarify\",\"agent\":null|\"agent-name\",\"confidence\":0..1,\"question\":null|\"...\"}."
)

class SuperRouterLLM:
    def __init__(self):
        self.llm = AzureLLM()

    def route(self, turn, *, active_agent: Optional[str], active_topic: Optional[str], sem_suggestion: Dict[str, Any] | None = None
             ) -> Tuple[str, float, Optional[Dict[str, Any]]]:
        ctx = {
            "TEXT": turn.text or "",
            "ACTIVE_AGENT": active_agent,
            "ACTIVE_TOPIC": active_topic,
            "SEM_SUGGESTION": sem_suggestion or {}
        }
        prompt = "Decide routing for this message based on context and rules:\n" + json.dumps(ctx, ensure_ascii=False)
        raw = self.llm.chat(
            messages=[{"role":"user","content": prompt}],
            system=SYSTEM,
            json_mode=True
        )
        try:
            data = json.loads(raw or "{}")
        except Exception:
            data = {}
        decision = data.get("decision") or "clarify"
        agent = data.get("agent")
        conf = float(data.get("confidence") or 0.0)
        question = data.get("question")
        log.info("super", extra={"stage":"router.super","decision":decision,"agent":agent,"conf":conf})

        if decision == "clarify":
            return "__clarify__", conf, {"question": question or "Could you clarify what you need?"}
        if decision == "handoff" and agent:
            return agent, conf, None
        if decision == "continue" and active_agent:
            return active_agent, conf, None
        # fallback
        return agent or active_agent or None, conf, None
