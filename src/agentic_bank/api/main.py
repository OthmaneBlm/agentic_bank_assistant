import os
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path

from agentic_bank.core.messages import TurnInput, TurnOutcome
from agentic_bank.core.memory import InMemoryStore
from agentic_bank.core.tooling import ToolRegistry, ToolExecutor

from agentic_bank.router.router import KeywordRouter
from agentic_bank.router.super_router_llm import SuperRouterLLM

from agentic_bank.agents.cards.agent_llm import CardControlAgentLLM, CardControlConfig
from agentic_bank.agents.cards.tools import register_card_tools

from agentic_bank.agents.appointment.agent_llm import AppointmentAgentLLM, ApptConfig
from agentic_bank.agents.appointment.tools import register_appointment_tools

from agentic_bank.agents.faq.agent_llm import FAQAgentLLM
from agentic_bank.agents.faq.tools import register_faq_tools
from agentic_bank.router.semantic_intents import SemanticIntents
import logging
# Load .env explicitly from project root
from dotenv import load_dotenv
import sys, pathlib

from agentic_bank.core.logging import setup_logging, get_logger
setup_logging()
log = get_logger("api")


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Agentic Bank v0.3.1 - All-in-One")

# CORS (handy for local UI)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def trace_requests(request: Request, call_next):
    # log method/path early
    log.debug(f"{request.method} {request.url.path}", extra={"stage":"http"})
    try:
        resp = await call_next(request)
        log.debug(f"{request.method} {request.url.path} -> {resp.status_code}", extra={"stage":"http"})
        return resp
    except Exception as e:
        log.exception(f"HTTP error: {e}", extra={"stage":"http"})
        raise

semantic_router = SemanticIntents()

ROOT = pathlib.Path(__file__).resolve().parents[3]
print(ROOT)
load_dotenv(dotenv_path=ROOT / ".env")
log = logging.getLogger("router")
log.setLevel(os.getenv("APP_LOG_LEVEL","INFO"))

app = FastAPI(title="Agentic Bank v0.3.1 - All-in-One")

memory = InMemoryStore()
tools = ToolRegistry()
register_card_tools(tools)
register_appointment_tools(tools)
register_faq_tools(tools)
tool_exec = ToolExecutor(tools)  # referenced by LLM agents

BASE = Path(__file__).resolve().parents[1]

AGENTS = {
    "agent-card-control-llm": CardControlAgentLLM(BASE / "agents/cards/prompts", CardControlConfig()),
    "agent-appointment-llm": AppointmentAgentLLM(BASE / "agents/appointment/prompts", ApptConfig()),
    "agent-faq-llm": FAQAgentLLM(BASE / "agents/faq/prompts"),
}

keyword_router = KeywordRouter()
super_router = SuperRouterLLM()

class ChatRequest(TurnInput):
    pass

class ChatResponse(BaseModel):
    agent: str
    confidence: float
    outcome: TurnOutcome
    followup: dict | None = None
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # Attach pending clarify if any
    pending = memory.session(req.sessionId).pop("router_pending", None)
    if pending:
        req.metadata = (req.metadata or {}) | {"router_prev_question": pending}

    # 1) keyword
    kw_agent, kw_conf = keyword_router.route(req)
    log.info("keyword route", extra={
        "stage":"route.kw", "turnId":req.turnId, "sessionId":req.sessionId,
        "agent":kw_agent, "conf":kw_conf
    })

    # 2) semantic (if you added the semantic router)
    try:
        from agentic_bank.router.semantic_intents import SemanticIntents
        global _SEM_ROUTER
        if "_SEM_ROUTER" not in globals():
            _SEM_ROUTER = SemanticIntents()
        sem_agent, sem_conf = _SEM_ROUTER.route(req.text or "")
        log.info("semantic route", extra={
            "stage":"route.sem", "turnId":req.turnId, "sessionId":req.sessionId,
            "agent":sem_agent, "conf":sem_conf
        })
    except Exception:
        sem_agent, sem_conf = "", 0.0

    best_agent, best_conf = (kw_agent, kw_conf)
    if sem_conf >= 0.80 and sem_conf >= kw_conf:
        best_agent, best_conf = (sem_agent, float(sem_conf))

    # 3) LLM router (clarify capable) if uncertain
    llm_agent, llm_conf, followup = "", 0.0, None
    if best_conf < 0.80:
        llm_agent, llm_conf, followup = super_router.route(req)
        log.info("llm route", extra={
            "stage":"route.llm", "turnId":req.turnId, "sessionId":req.sessionId,
            "agent":llm_agent, "conf":llm_conf
        })
        if llm_agent == "__clarify__" and followup:
            memory.session(req.sessionId)["router_pending"] = followup
            log.info("clarify ask", extra={
                "stage":"route.clarify", "turnId":req.turnId, "sessionId":req.sessionId
            })
            return ChatResponse(
                agent="__clarify__",
                confidence=0.0,
                followup=followup,
                outcome=TurnOutcome(replyText=followup["question"], fsmState="ROUTER_CLARIFY")
            )
        if llm_conf > best_conf:
            best_agent, best_conf = llm_agent, llm_conf

    agent_name, conf = best_agent, best_conf
    if conf < 0.5:
        agent_name, conf = "agent-faq-llm", 0.5

    # run agent
    agent = AGENTS.get(agent_name)
    if not agent:
        log.error("agent not found", extra={"stage":"route.final", "agent":agent_name})
        raise HTTPException(status_code=500, detail=f"Agent not found: {agent_name}")

    log.info("route final", extra={
        "stage":"route.final", "turnId":req.turnId, "sessionId":req.sessionId,
        "agent":agent_name, "conf":conf
    })

    session_mem = memory.session(req.sessionId).setdefault(agent_name, {})
    outcome = agent.run(req, session_mem, tool_exec)
    if outcome.fsmState:
        session_mem["fsm"] = outcome.fsmState

    log.info("agent outcome", extra={
        "stage":"agent.outcome", "turnId":req.turnId, "sessionId":req.sessionId,
        "agent":agent_name
    })
    return ChatResponse(agent=agent_name, confidence=conf, outcome=outcome)
