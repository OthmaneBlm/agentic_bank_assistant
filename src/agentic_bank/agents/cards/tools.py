# agentic_bank/agents/card_control/tools.py
from agentic_bank.core.tooling import Tool, ToolRegistry
from typing import Dict, Any

def register_card_tools(registry: ToolRegistry):
    def block_card(args: Dict[str, Any]):
        card_number = args.get("card_number", "unknown")
        reason = args.get("reason", "unspecified")
        confirm = args.get("confirm", False)
        if not confirm:
            raise ValueError("User did not confirm card block.")
        return {
            "status": "blocked",
            "card_number": card_number,
            "reason": reason
        }

    def order_replacement(args: Dict[str, Any]):
        delivery = args.get("delivery", "mail")
        return {
            "status": "ordered",
            "delivery": delivery,
            "eta_days": 5
        }

    registry.register(Tool("cards.block", block_card, "Block a payment card"))
    registry.register(Tool("cards.order_replacement", order_replacement, "Order a replacement card"))
