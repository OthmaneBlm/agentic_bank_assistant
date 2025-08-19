# src/agentic_bank/api/main.py
import os
import uuid
from pathlib import Path
from time import time
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from dotenv import load_dotenv
load_dotenv("../.env")
# --- Logging ---
from agentic_bank.core.logging import setup_logging, get_logger

# Core types & infra
from agentic_bank.core.messages import TurnInput, UserIdentity
from agentic_bank.core.memory import InMemoryStore
from agentic_bank.core.tooling import ToolRegistry, ToolExecutor

# Profiles & conversation history
from agentic_bank.core.profile import ProfileStore
from agentic_bank.core.conv_memory import ConversationMemory
from agentic_bank.core.utterance import is_acknowledgement

# Routers (standardized ensemble)
from agentic_bank.router.router import KeywordRouter, EnsembleRouter, EnsembleConfig
from agentic_bank.router.semantic_intents import SemanticIntents
from agentic_bank.router.llm_intent import LLMIntentClassifier
from agentic_bank.router.topic_shift import TopicShiftDetector
from agentic_bank.router.super_router_llm import SuperRouterLLM  # optional fallback

# Agents + tools
from agentic_bank.agents.cards.agent_llm import CardControlAgentLLM, CardControlConfig
from agentic_bank.agents.cards.tools import register_card_tools
from agentic_bank.agents.appointment.agent_llm import AppointmentAgentLLM, ApptConfig
from agentic_bank.agents.appointment.tools import register_appointment_tools
from agentic_bank.agents.faq.agent_llm import FAQAgentLLM
from agentic_bank.agents.faq.tools import register_faq_tools

# ------------------------------------------------------------------------------
# Locate project roots:
# main.py is at: <project>/src/agentic_bank/api/main.py
API_DIR = Path(__file__).resolve().parent                # .../src/agentic_bank/api
PKG_ROOT = API_DIR.parent                                # .../src/agentic_bank
SRC_ROOT = PKG_ROOT.parent                               # .../src
PROJECT_ROOT = SRC_ROOT.parent                           # <project>

# Data paths match original intent
ROOT = PROJECT_ROOT

# ------------------------------------------------------------------------------
app = FastAPI(title="Agentic Bank – API")

setup_logging()
log = get_logger("api")
log.info(
    f"ENV: endpoint={os.getenv('AZURE_OPENAI_ENDPOINT')} "
    f"deployment={os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o')}",
    extra={"stage": "api.env"}
)

# ------------------------------------------------------------------------------
# Stores & registries
memory = InMemoryStore()

PROFILE = ProfileStore(ROOT / "data" / "profiles")
CONV = ConversationMemory(ROOT / "data" / "conversations")

tools = ToolRegistry()
register_card_tools(tools)
register_appointment_tools(tools)
register_faq_tools(tools)
tool_exec = ToolExecutor(tools)

# Agents (IMPORTANT: pass Path, not str)
AGENTS = {
    "agent-card-control-llm": CardControlAgentLLM(
        PKG_ROOT / "agents" / "cards" / "prompts", CardControlConfig()
    ),
    "agent-appointment-llm": AppointmentAgentLLM(
        PKG_ROOT / "agents" / "appointment" / "prompts", ApptConfig()
    ),
    "agent-faq-llm": FAQAgentLLM(
        PKG_ROOT / "agents" / "faq" / "prompts"
    ),
}

# Routers (ensemble)
keyword_router = KeywordRouter()
semantic_router = SemanticIntents()
intent_clf = LLMIntentClassifier()
topic_shift = TopicShiftDetector()
ensemble = EnsembleRouter(keyword_router, semantic_router, intent_clf, topic_shift, EnsembleConfig())
super_router = SuperRouterLLM()  # optional tie-breaker

# ------------------------------------------------------------------------------
# Simple password auth (mirrors Chainlit demo password)
def require_demo_password(x_demo_password: Optional[str] = Header(default=None)):
    expected = os.getenv("CHAINLIT_DEMO_PASSWORD", "demo")
    if not x_demo_password or x_demo_password != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

# ------------------------------------------------------------------------------
# API Models
class StartRequest(BaseModel):
    userId: Optional[str] = None

class StartResponse(BaseModel):
    sessionId: str
    userId: str
    greeting: str
    profile: Dict[str, Any]

class MessageRequest(BaseModel):
    sessionId: str
    userId: Optional[str] = None
    text: str = Field(default="")

class ToolEcho(BaseModel):
    key: str
    value: Any

class MessageResponse(BaseModel):
    replyText: str
    agent: Optional[str] = None
    confidence: float = 0.0
    isTerminal: bool = False
    handledTopic: Optional[str] = None
    debugSignals: List[str] = Field(default_factory=list)
    toolOutputs: List[ToolEcho] = Field(default_factory=list)
    lastTopic: Optional[str] = None
    activeAgent: Optional[str] = None

# ------------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True}

@app.post("/start", response_model=StartResponse)
def start(req: StartRequest, _auth=Depends(require_demo_password)):
    user_id = (req.userId or "demo").strip() or "demo"

    profile = PROFILE.load(user_id)
    profile.fullName = profile.fullName or user_id.capitalize()
    profile.tier = profile.tier or "standard"
    PROFILE.save(profile)

    greeting = (
        f"Welcome back, {profile.fullName}! ({profile.tier.title()} member)\n"
        "- Block/unblock a card\n- Book an appointment\n- Ask an FAQ\n"
        "I’ll close each task and hand off to the right agent for new topics."
    )

    session_id = str(uuid.uuid4())
    sess = memory.session(session_id)
    sess["user_id"] = user_id
    sess["last_was_terminal"] = False

    return StartResponse(
        sessionId=session_id,
        userId=user_id,
        greeting=greeting,
        profile=profile.model_dump()
    )

@app.post("/message", response_model=MessageResponse)
def message(req: MessageRequest, _auth=Depends(require_demo_password)):
    session_id = req.sessionId
    sess = memory.session(session_id)
    user_id = (req.userId or sess.get("user_id") or "demo").strip() or "demo"
    text = req.text or ""

    # persist user's message
    CONV.append(user_id, session_id, role="user", content=text, meta={})

    # load profile + recent history
    profile = PROFILE.load(user_id)
    recent = CONV.last_n(user_id, session_id, n=8)

    # build TurnInput
    turn = TurnInput(
        turnId=str(uuid.uuid4()),
        sessionId=session_id,
        channel="web",
        user=UserIdentity(userId=user_id, kycVerified=True, scopes=["card:write", "appointments:write"]),
        text=text,
        metadata={
            "profile": profile.model_dump(),
            "recent_messages": recent
        }
    )

    # carry pending clarifier
    pending = sess.pop("router_pending", None)
    if pending:
        turn.metadata = (turn.metadata or {}) | {"router_prev_question": pending}

    active_agent = sess.get("active_agent")
    log.info("turn in", extra={"stage": "api.turn", "user": user_id, "sessionId": session_id})

    # --- Acknowledgement short-circuit after a terminal turn ---
    if sess.get("last_was_terminal"):
        last_t = float(sess.get("last_terminal_at", 0.0) or 0.0)
        if is_acknowledgement(text) and (time() - last_t) <= 120:
            closing = "Great — I’ll close this issue. If you need anything else, just tell me."
            CONV.append(user_id, session_id, role="assistant", content=closing, meta={"agent": "system"})
            return MessageResponse(
                replyText=closing,
                agent="system",
                confidence=1.0,
                isTerminal=True,
                handledTopic=sess.get("last_topic") or None,
                lastTopic=sess.get("last_topic") or None,
                activeAgent=None
            )

    # --------------- If an agent is active, let it handle this turn ---------------
    if active_agent:
        agent = AGENTS.get(active_agent)
        if agent:
            session_mem = sess.setdefault(active_agent, {})
            outcome = agent.run(turn, session_mem, tool_exec)

            # Promote agent facts
            if any(isinstance(k, str) and k.startswith("__fact_") for k in session_mem.keys()):
                facts = sess.setdefault("facts", {})
                for k, v in list(session_mem.items()):
                    if isinstance(k, str) and k.startswith("__fact_"):
                        facts[k] = v

            tool_out = []
            for k, v in session_mem.items():
                if isinstance(k, str) and k.startswith("tool:"):
                    tool_out.append(ToolEcho(key=k, value=v))

            CONV.append(user_id, session_id, role="assistant", content=outcome.replyText or "", meta={"agent": active_agent})

            if outcome.isTerminal:
                sess.pop("active_agent", None)
                sess["last_topic"] = outcome.handledTopic
                sess["last_topic_time"] = time()
                sess["active_topic"] = None
                sess["last_was_terminal"] = True
                sess["last_terminal_at"] = time()
                log.info("agent terminal", extra={"stage": "api.agent.terminal", "agent": active_agent, "topic": outcome.handledTopic})
                return MessageResponse(
                    replyText=outcome.replyText or "(no text)",
                    agent=active_agent,
                    confidence=1.0,
                    isTerminal=True,
                    handledTopic=outcome.handledTopic,
                    toolOutputs=tool_out,
                    lastTopic=sess.get("last_topic") or None,
                    activeAgent=None
                )
            else:
                log.info("continue agent", extra={"stage": "api.continue", "agent": active_agent})
                return MessageResponse(
                    replyText=outcome.replyText or "(no text)",
                    agent=active_agent,
                    confidence=1.0,
                    isTerminal=False,
                    handledTopic=outcome.handledTopic,
                    toolOutputs=tool_out,
                    lastTopic=sess.get("last_topic") or None,
                    activeAgent=active_agent
                )
        else:
            sess.pop("active_agent", None)

    # --------------- No active agent → Ensemble routing ---------------
    facts = sess.get("facts", {})
    last_topic = sess.get("last_topic")
    last_topic_time = sess.get("last_topic_time")

    result = ensemble.decide(
        turn,
        last_topic=last_topic,
        last_topic_time=last_topic_time,
        session_facts=facts
    )

    debug_signals = [f"{s.source[:3]}={s.agent or '-'}({s.confidence:.2f})" for s in result.signals] or ["no-signals"]

    # Clarify branch
    if result.agent == "__clarify__" and result.clarify:
        sess["router_pending"] = result.clarify
        q = f"(Clarify) {result.clarify['question']}"
        return MessageResponse(
            replyText=q,
            agent="__clarify__",
            confidence=1.0,
            isTerminal=False,
            handledTopic=None,
            debugSignals=debug_signals,
            lastTopic=sess.get("last_topic") or None,
            activeAgent=None
        )

    agent_name, conf = result.agent, result.confidence

    # Optional: escalate to SuperRouter only if ensemble is weak
    if (not agent_name) or conf < 0.75:
        try:
            agent_name2, conf2, followup = super_router.route(
                turn,
                active_agent=None,
                active_topic=last_topic,
                sem_suggestion={"best": agent_name, "conf": conf}
            )
            if agent_name2 == "__clarify__" and followup:
                sess["router_pending"] = followup
                q = f"(Clarify) {followup['question']}"
                return MessageResponse(
                    replyText=q,
                    agent="__clarify__",
                    confidence=max(conf, conf2),
                    isTerminal=False,
                    handledTopic=None,
                    debugSignals=debug_signals,
                    lastTopic=sess.get("last_topic") or None,
                    activeAgent=None
                )
            if agent_name2:
                agent_name, conf = agent_name2, max(conf, conf2)
        except Exception as e:
            log.error(f"super route error: {e}", extra={"stage":"api.route.super.err"})

    if not agent_name:
        return MessageResponse(
            replyText="Sorry, I couldn't route that. Could you rephrase?",
            agent=None,
            confidence=conf or 0.0,
            isTerminal=False,
            handledTopic=None,
            debugSignals=debug_signals,
            lastTopic=sess.get("last_topic") or None,
            activeAgent=None
        )

    agent = AGENTS.get(agent_name)
    if not agent:
        return MessageResponse(
            replyText=f"Agent not found: {agent_name}",
            agent=None,
            confidence=conf or 0.0,
            isTerminal=False,
            handledTopic=None,
            debugSignals=debug_signals,
            lastTopic=sess.get("last_topic") or None,
            activeAgent=None
        )

    # Execute chosen agent
    sess["last_was_terminal"] = False  # we are engaging
    session_mem = sess.setdefault(agent_name, {})
    outcome = agent.run(turn, session_mem, tool_exec)

    # Promote facts
    if any(isinstance(k, str) and k.startswith("__fact_") for k in session_mem.keys()):
        facts = sess.setdefault("facts", {})
        for k, v in list(session_mem.items()):
            if isinstance(k, str) and k.startswith("__fact_"):
                facts[k] = v

    tool_out = []
    for k, v in session_mem.items():
        if isinstance(k, str) and k.startswith("tool:"):
            tool_out.append(ToolEcho(key=k, value=v))

    if outcome.isTerminal:
        sess["last_topic"] = outcome.handledTopic
        sess["last_topic_time"] = time()
        sess.pop("active_agent", None)
        sess["active_topic"] = None
    else:
        sess["active_agent"] = agent_name
        sess["active_topic"] = outcome.handledTopic

    log.info("outcome", extra={
        "stage":"api.out",
        "user": user_id,
        "sessionId": session_id,
        "agent": agent_name,
        "terminal": outcome.isTerminal,
        "topic": outcome.handledTopic
    })

    return MessageResponse(
        replyText=outcome.replyText or "(no text)",
        agent=agent_name,
        confidence=float(conf or 0.0),
        isTerminal=bool(outcome.isTerminal),
        handledTopic=outcome.handledTopic,
        debugSignals=debug_signals,
        toolOutputs=tool_out,
        lastTopic=sess.get("last_topic") or None,
        activeAgent=sess.get("active_agent") or None
    )
