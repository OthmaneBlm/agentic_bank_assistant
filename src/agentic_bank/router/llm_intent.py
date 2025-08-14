from __future__ import annotations
from typing import Dict, Any, Optional, Tuple, List
import json
from agentic_bank.core.llm.azure import AzureLLM
from agentic_bank.core.logging import get_logger

log = get_logger("router.llm_intent")

SYSTEM = (
  "You are a banking intent classifier. "
  "Given the user's latest message, RECENT_MESSAGES and SESSION_FACTS, return a single top intent with confidence (0..1) and slots.\n"
  "Return STRICT JSON with keys: {intent, confidence, slots}.\n"
  "Allowed intents: card_block, card_replacement, appointment_booking, faq, smalltalk, closing, other.\n"
  "Rules:\n"
  "- Disambiguate short follow-ups using RECENT_MESSAGES and SESSION_FACTS (e.g., card already blocked).\n"
  "- If last topic was cards and phrasing implies replacement ('order a new one'), classify card_replacement.\n"
  "- 'thanks/ok/yes' after resolution => smalltalk or closing.\n"
  "- Only use high confidence (>0.75) when certain.\n"
  "Respond JSON only."
)

FEWSHOTS: List[Dict[str, Any]] = [
  {
    "USER_TEXT": "order a new one please",
    "RECENT_MESSAGES": [{"role":"assistant","content":"Your card is now blocked."}],
    "SESSION_FACTS": {"__fact_card_blocked": True},
    "LAST_TOPIC": "card_block",
    "EXPECT": {"intent":"card_replacement","confidence":0.85}
  },
  {
    "USER_TEXT": "book me a slot at the branch",
    "RECENT_MESSAGES": [],
    "SESSION_FACTS": {},
    "LAST_TOPIC": "",
    "EXPECT": {"intent":"appointment_booking","confidence":0.8}
  },
  {
    "USER_TEXT": "ok thanks",
    "RECENT_MESSAGES": [{"role":"assistant","content":"Resolved."}],
    "SESSION_FACTS": {},
    "LAST_TOPIC": "card_block",
    "EXPECT": {"intent":"smalltalk","confidence":0.8}
  }
]

class LLMIntentClassifier:
    def __init__(self):
        self.llm = AzureLLM()

    def classify(
        self,
        *,
        user_text: str,
        recent_messages: list[dict[str, Any]] | None,
        session_facts: dict[str, Any] | None,
        last_topic: Optional[str] = None
    ) -> Tuple[str, float, Dict[str, Any]]:
        ctx = {
            "USER_TEXT": user_text or "",
            "RECENT_MESSAGES": recent_messages or [],
            "SESSION_FACTS": session_facts or {},
            "LAST_TOPIC": last_topic or "",
            "FEWSHOTS": FEWSHOTS
        }
        prompt = (
            "Classify the intent based on the following JSON context. "
            "Return {\"intent\":\"...\",\"confidence\":0..1,\"slots\":{...}}.\n"
            f"{json.dumps(ctx, ensure_ascii=False)}"
        )
        raw = self.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system=SYSTEM,
            json_mode=True,
            temperature=0.0
        )
        try:
            data = json.loads(raw or "{}")
        except Exception:
            data = {}
        intent = str(data.get("intent") or "other")
        conf = float(data.get("confidence") or 0.0)
        slots = data.get("slots") or {}
        log.info("intent", extra={"stage":"router.llm.intent","intent":intent,"conf":conf})
        return intent, conf, slots
