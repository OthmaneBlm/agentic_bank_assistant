# --- Bootstrap: path + .env (works from any CWD) ------------------------------
from pathlib import Path
import sys, os, uuid

# repo root:   chainlit/app.py -> parents[2]
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# from dotenv import load_dotenv
# load_dotenv(ROOT / ".env")

# If you use BASE later for prompts/data:
BASE = SRC / "agentic_bank"

import chainlit as cl
from pathlib import Path
from time import time

# Logging
from agentic_bank.core.logging import setup_logging, get_logger
setup_logging()
cl_log = get_logger("chainlit")
cl_log.info(
    f"ENV: endpoint={os.getenv('AZURE_OPENAI_ENDPOINT')} deployment={os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o')}",
    extra={"stage": "ui.env"}
)

# --- Chainlit auth (demo password) ---
@cl.password_auth_callback
def auth_callback(username: str, password: str):
    expected = os.getenv("CHAINLIT_DEMO_PASSWORD", "demo")
    if password == expected and username:
        return cl.User(identifier=username, metadata={"role": "USER"})
    return None

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
# Stores & registries
memory = InMemoryStore()

PROFILE = ProfileStore(ROOT / "data" / "profiles")
CONV = ConversationMemory(ROOT / "data" / "conversations")

tools = ToolRegistry()
register_card_tools(tools)
register_appointment_tools(tools)
register_faq_tools(tools)
tool_exec = ToolExecutor(tools)

# Agents
BASE = Path(__file__).resolve().parents[1] / "src" / "agentic_bank"
AGENTS = {
    "agent-card-control-llm": CardControlAgentLLM(BASE / "agents/cards/prompts", CardControlConfig()),
    "agent-appointment-llm": AppointmentAgentLLM(BASE / "agents/appointment/prompts", ApptConfig()),
    "agent-faq-llm": FAQAgentLLM(BASE / "agents/faq/prompts"),
}

# Routers (ensemble)
keyword_router = KeywordRouter()               # or KeywordRouter(patterns=your_dict)
semantic_router = SemanticIntents()
intent_clf = LLMIntentClassifier()
topic_shift = TopicShiftDetector()
ensemble = EnsembleRouter(keyword_router, semantic_router, intent_clf, topic_shift, EnsembleConfig())
super_router = SuperRouterLLM()                # optional tie-breaker
# ------------------------------------------------------------------------------

@cl.on_chat_start
async def start():
    app_user = cl.user_session.get("user")
    user_id = getattr(app_user, "identifier", None) or "demo"

    profile = PROFILE.load(user_id)
    profile.fullName = profile.fullName or user_id.capitalize()
    profile.tier = profile.tier or "standard"
    PROFILE.save(profile)

    greeting = (
        f"Welcome back, {profile.fullName}! ({profile.tier.title()} member)\n"
        "- Block/unblock a card\n- Book an appointment\n- Ask an FAQ\n"
        "I’ll close each task and hand off to the right agent for new topics."
    )
    await cl.Message(content=greeting).send()

    cl.user_session.set("session_id", str(uuid.uuid4()))
    cl.user_session.set("user_id", user_id)

@cl.on_message
async def main(message: cl.Message):
    session_id = cl.user_session.get("session_id")
    user_id = cl.user_session.get("user_id") or "demo"
    text = message.content or ""

    # Persist user's message
    CONV.append(user_id, session_id, role="user", content=text, meta={})

    # Load profile + recent history
    profile = PROFILE.load(user_id)
    recent = CONV.last_n(user_id, session_id, n=8)

    # Build TurnInput
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

    # Carry pending clarifier into metadata
    pending = memory.session(session_id).pop("router_pending", None)
    if pending:
        turn.metadata = (turn.metadata or {}) | {"router_prev_question": pending}

    sess = memory.session(session_id)
    active_agent = sess.get("active_agent")

    cl_log.info("turn in", extra={"stage": "ui.turn", "user": user_id, "sessionId": session_id})

    # --- Acknowledgement short-circuit after a terminal turn ---
    if sess.get("last_was_terminal"):
        last_t = float(sess.get("last_terminal_at", 0.0) or 0.0)
        if is_acknowledgement(text) and (time() - last_t) <= 120:
            closing = "Great — I’ll close this issue. If you need anything else, just tell me."
            await cl.Message(content=closing).send()
            CONV.append(user_id, session_id, role="assistant", content=closing, meta={"agent": "system"})
            return

    # --------------- If an agent is active, let it handle this turn ---------------
    if active_agent:
        agent = AGENTS.get(active_agent)
        if agent:
            session_mem = sess.setdefault(active_agent, {})
            outcome = agent.run(turn, session_mem, tool_exec)

            # Promote agent facts to session facts
            if any(isinstance(k, str) and k.startswith("__fact_") for k in session_mem.keys()):
                facts = sess.setdefault("facts", {})
                for k, v in list(session_mem.items()):
                    if isinstance(k, str) and k.startswith("__fact_"):
                        facts[k] = v

            # Reply
            await cl.Message(content=outcome.replyText or "(no text)").send()
            for k, v in session_mem.items():
                if isinstance(k, str) and k.startswith("tool:"):
                    await cl.Message(author="tool", content=f"{k} → {v}").send()
            CONV.append(user_id, session_id, role="assistant", content=outcome.replyText or "", meta={"agent": active_agent})

            if outcome.isTerminal:
                sess.pop("active_agent", None)
                sess["last_topic"] = outcome.handledTopic
                sess["last_topic_time"] = time()
                sess["active_topic"] = None
                sess["last_was_terminal"] = True
                sess["last_terminal_at"] = time()
                cl_log.info("agent terminal", extra={"stage": "ui.agent.terminal", "agent": active_agent, "topic": outcome.handledTopic})
                return
            else:
                cl_log.info("continue agent", extra={"stage": "ui.continue", "agent": active_agent})
                return
        else:
            sess.pop("active_agent", None)
            return

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

    # visible debug of signals (kw/sem/llm/topic)
    await cl.Message(
        author="debug",
        content=" | ".join([f"{s.source[:3]}={s.agent or '-'}({s.confidence:.2f})" for s in result.signals]) or "no-signals"
    ).send()

    # Clarify branch
    if result.agent == "__clarify__" and result.clarify:
        sess["router_pending"] = result.clarify
        await cl.Message(content=f"(Clarify) {result.clarify['question']}").send()
        return

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
                await cl.Message(content=f"(Clarify) {followup['question']}").send()
                return
            if agent_name2:
                agent_name, conf = agent_name2, max(conf, conf2)
        except Exception as e:
            cl_log.error(f"super route error: {e}", extra={"stage":"ui.route.super.err"})

    if not agent_name:
        await cl.Message(content="Sorry, I couldn't route that. Could you rephrase?").send()
        return

    agent = AGENTS.get(agent_name)
    if not agent:
        await cl.Message(content=f"Agent not found: {agent_name}").send()
        return

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

    if outcome.isTerminal:
        sess["last_topic"] = outcome.handledTopic
        sess["last_topic_time"] = time()
        sess.pop("active_agent", None)
        sess["active_topic"] = None
    else:
        sess["active_agent"] = agent_name
        sess["active_topic"] = outcome.handledTopic

    await cl.Message(content=f"→ **{agent_name}** (confidence {conf:.2f})").send()
    await cl.Message(content=outcome.replyText or "(no text)").send()

    for k, v in session_mem.items():
        if isinstance(k, str) and k.startswith("tool:"):
            await cl.Message(author="tool", content=f"{k} → {v}").send()

    CONV.append(user_id, session_id, role="assistant", content=outcome.replyText or "", meta={"agent": agent_name})

    cl_log.info("outcome", extra={
        "stage":"ui.out",
        "user": user_id,
        "sessionId": session_id,
        "agent": agent_name,
        "terminal": outcome.isTerminal,
        "topic": outcome.handledTopic
    })

    # final debug line
    await cl.Message(
        author="debug",
        content=f"final={agent_name or '-'}({conf:.2f}) | last_topic={sess.get('last_topic') or '-'} active={sess.get('active_agent') or '-'}"
    ).send()
