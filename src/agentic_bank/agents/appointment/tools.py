# agentic_bank/agents/appointment/tools.py
from agentic_bank.core.tooling import Tool, ToolRegistry
from typing import Dict, Any

def register_appointment_tools(registry: ToolRegistry):
    def book_appointment(args: Dict[str, Any]):
        branch = args.get("branch")
        date = args.get("date")
        topic = args.get("topic")
        if not branch or not date or not topic:
            raise ValueError("Missing required appointment fields")
        
        return {
            "status": "booked",
            "branch": branch,
            "date": date,
            "topic": topic,
            "confirmation_number": "APT12345"
        }

    registry.register(
        Tool("appointments.book", book_appointment, "Book a branch appointment")
    )
