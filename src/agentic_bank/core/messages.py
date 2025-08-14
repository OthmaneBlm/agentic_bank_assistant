from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

Channel = Literal["web","mobile","ivr","whatsapp"]

class UserIdentity(BaseModel):
    userId: str
    kycVerified: bool = False
    scopes: List[str] = Field(default_factory=list)

class TurnInput(BaseModel):
    turnId: str
    sessionId: str
    channel: Channel
    user: UserIdentity
    text: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    locale: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class ToolCall(BaseModel):
    toolId: str
    arguments: Dict[str, Any]
    traceId: Optional[str] = None

class TurnOutcome(BaseModel):
    replyText: Optional[str] = None
    toolCalls: Optional[List[ToolCall]] = None
    nextAgent: Optional[str] = None
    fsmState: Optional[str] = None
    memoryWrites: Optional[Dict[str, Any]] = None
    safetyFlags: Optional[List[str]] = None
    isTerminal: bool = False            # agent considers this flow resolved/closed
    handledTopic: Optional[str] = None  # short tag like "card_block", "appointment_booking", "faq"