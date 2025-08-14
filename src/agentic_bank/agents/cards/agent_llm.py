import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from agentic_bank.core.llm.azure import AzureLLM
from agentic_bank.core.messages import TurnOutcome

class CardControlConfig:
    def __init__(self):
        self.model = "gpt-4o"

class CardControlAgentLLM:
    def __init__(self, prompts_dir: Path, config: Optional[CardControlConfig] = None):
        self.prompts_dir = prompts_dir
        self.config = config or CardControlConfig()
        self.llm = AzureLLM()
        self.system_prompt = (self.prompts_dir / "system.md").read_text()

        # Mock tool schema for blocking a card
        self.tools_schema: List[Dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": "block_card",
                    "description": "Blocks a user's bank card.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "card_type": {
                                "type": "string",
                                "description": "The type of card (debit, credit, prepaid)."
                            },
                            "card_number": {
                                "type": "string",
                                "description": "Full or masked card number (e.g., ****1234)."
                            },
                            "confirmation": {
                                "type": "boolean",
                                "description": "Whether the user confirmed the block."
                            },
                            "reason": {
                                "type": "string",
                                "description": "Reason for blocking (lost, stolen, fraud, damaged)."
                            }
                        },
                        "required": ["card_type", "card_number", "confirmation", "reason"]
                    }
                }
            }
        ]

    def llm_infer(self, context: Dict[str, Any], tool_exec) -> str:
        """
        Sends the conversation context to the LLM and lets it decide:
        - What to reply to the user
        - Whether it can call `block_card`
        """
        system_message = self.system_prompt.strip()

        user_message = f"""
            You are a banking assistant that handles card-related issues: blocking, unblocking, and replacements.

            Conversation so far:
            {json.dumps(context.get("recent_messages", []), ensure_ascii=False, indent=2)}

            Facts collected so far:
            {json.dumps(context.get("facts", {}), ensure_ascii=False, indent=2)}

            User's latest message:
            {context.get("user_message")}

            Your job:
            1. Collect the following details if not already known:
            - card_type (debit, credit, prepaid)
            - card_number (full or masked)
            - confirmation (boolean)
            - reason (lost, stolen, fraud, damaged)
            2. Once all are collected and user confirmed, call the `block_card` tool with the details.
            3. Mark the task as terminal after a successful block.

            Output JSON with:
            - replyText: your reply to the user
            - isTerminal: true if card is blocked or request is complete
            - handledTopic: "card_control"
            - facts: store any new details
            """.strip()

        messages = [{"role": "user", "content": user_message}]
        text, summaries = self.llm.chat_with_tools(
            messages=messages,
            tools=self.tools_schema,
            system=system_message,
            tool_executor=tool_exec
        )

        return text, summaries

    def run(self, turn, session_mem, tool_exec):
        """
        Called by app.py — lets the LLM handle flow and optionally call `block_card`.
        """
        context = {
            "recent_messages": turn.metadata.get("recent_messages", []),
            "facts": session_mem,
            "user_message": turn.text
        }

        raw, tool_summaries = self.llm_infer(context, tool_exec)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {
                "replyText": raw.strip(),
                "isTerminal": False,
                "handledTopic": "card_control"
            }

        # Save extracted facts
        if isinstance(parsed.get("facts"), dict):
            session_mem.update(parsed["facts"])

        # You can log or show tool call summaries here
        if tool_summaries:
            for s in tool_summaries:
                print(f"Tool called: {s}")

        return TurnOutcome(
            replyText=parsed.get("replyText", "").strip(),
            isTerminal=bool(parsed.get("isTerminal", False)),
            handledTopic=parsed.get("handledTopic", "card_control")
        )
