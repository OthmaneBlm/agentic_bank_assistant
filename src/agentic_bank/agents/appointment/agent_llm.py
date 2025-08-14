import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from agentic_bank.core.llm.azure import AzureLLM
from agentic_bank.core.messages import TurnOutcome

class ApptConfig:
    def __init__(self):
        self.model = "gpt-4o"

class AppointmentAgentLLM:
    def __init__(self, prompts_dir: Path, config: Optional[ApptConfig] = None):
        self.prompts_dir = prompts_dir
        self.config = config or ApptConfig()
        self.llm = AzureLLM()
        self.system_prompt = (self.prompts_dir / "system.md").read_text()

        # Optional: define tool schema for booking/checking availability
        self.tools_schema: List[Dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": "appointments_check_availability",
                    "description": "Check branch availability for a given date/topic.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "branch": {"type": "string", "enum": ["central", "east", "west"]},
                            "date": {"type": "string"},
                            "topic": {"type": "string"}
                        },
                        "required": ["branch", "date", "topic"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "appointments_create",
                    "description": "Create an appointment.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "branch": {"type": "string"},
                            "date": {"type": "string"},
                            "topic": {"type": "string"}
                        },
                        "required": ["branch", "date", "topic"]
                    }
                }
            }
        ]

    def llm_infer(self, context: Dict[str, Any]) -> str:
        """
        Send the prompt to the LLM with context and return raw string.
        """
        system_message = self.system_prompt.strip()

        user_message = f"""
You are a banking assistant that books branch appointments.

Conversation so far:
{json.dumps(context.get("recent_messages", []), ensure_ascii=False, indent=2)}

Facts collected so far:
{json.dumps(context.get("facts", {}), ensure_ascii=False, indent=2)}

User's latest message:
{context.get("user_message")}

Your job:
- Collect the missing details: branch, date, topic.
- Once all details are collected, confirm booking (using tools if needed).
- Decide if the task is fully completed.
- Respond naturally to the user.
- Output JSON with:
  - replyText: what to say to the user
  - isTerminal: true if the appointment is booked or the request is complete
  - handledTopic: "appointment_booking"
  - (optional) facts: any extracted details like branch/date/topic

Example JSON output:
{{
  "replyText": "Your appointment is booked at Central branch on 2025-08-20 for mortgage advice.",
  "isTerminal": true,
  "handledTopic": "appointment_booking",
  "facts": {{
      "branch": "central",
      "date": "2025-08-20",
      "topic": "mortgage"
  }}
}}
""".strip()

        messages = [{"role": "user", "content": user_message}]
        raw = self.llm.chat(messages, system=system_message)
        return raw

    def run(self, turn, session_mem, tool_exec):
        """
        Called by app.py — uses LLM to decide conversation flow.
        """
        context = {
            "recent_messages": turn.metadata.get("recent_messages", []),
            "facts": session_mem,
            "user_message": turn.text
        }

        raw = self.llm_infer(context)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {
                "replyText": raw.strip(),
                "isTerminal": False,
                "handledTopic": "appointment_booking"
            }

        # Store extracted facts in session memory
        if isinstance(parsed.get("facts"), dict):
            session_mem.update(parsed["facts"])

        return TurnOutcome(
            replyText=parsed.get("replyText", "").strip(),
            isTerminal=bool(parsed.get("isTerminal", False)),
            handledTopic=parsed.get("handledTopic", "appointment_booking")
        )
