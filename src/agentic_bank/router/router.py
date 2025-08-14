from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
from pydantic import BaseModel, Field
from dataclasses import dataclass
import os, re
from agentic_bank.core.messages import TurnInput
from agentic_bank.core.logging import get_logger

log = get_logger("router.core")

# ---------------- Shared routing types ----------------

class RouteSignal(BaseModel):
    source: str                           # "keyword" | "semantic" | "llm" | "topic"
    agent: Optional[str] = None
    confidence: float = 0.0
    details: Dict[str, Any] = Field(default_factory=dict)

class RouterResult(BaseModel):
    agent: Optional[str] = None          # chosen agent or None
    confidence: float = 0.0
    clarify: Optional[Dict[str, Any]] = None  # {"question": "..."} if clarifier needed
    signals: List[RouteSignal] = Field(default_factory=list)

# ---------------- Keyword router ----------------

class KeywordRouter:
    """
    Very fast lexical router. Configure in code or load from YAML if you prefer.
    matches: { "agent-name": [patterns...] }
    """
    def __init__(self, patterns: Dict[str, List[str]] | None = None):
        # Default patterns (minimal, tune freely)
        self.patterns = patterns or {
            "agent-card-control-llm": [
                r"\b(block|freeze|lock)\b",
                r"\b(card|stolen|lost|fraud)\b",
                r"\b(replacement|reissue)\b",
            ],
            "agent-appointment-llm": [
                r"\b(appointment|schedule|book|meeting|visit)\b",
            ],
            "agent-faq-llm": [
                r"\b(limit|fees?|cutoff|how (do|to)|where|what)\b",
            ],
        }
        self._compiled: Dict[str, List[re.Pattern]] = {
            a: [re.compile(pat, re.I) for pat in pats] for a, pats in self.patterns.items()
        }

    def route(self, turn: TurnInput) -> Tuple[Optional[str], float, RouteSignal]:
        text = (turn.text or "").lower()
        if not text:
            return None, 0.0, RouteSignal(source="keyword", agent=None, confidence=0.0)
        scores: Dict[str, int] = {}
        for agent, pats in self._compiled.items():
            hit = sum(1 for pat in pats if pat.search(text))
            if hit:
                scores[agent] = hit
        if not scores:
            sig = RouteSignal(source="keyword", agent=None, confidence=0.0, details={"scores": {}})
            return None, 0.0, sig
        # normalize to [0..1] by dividing by max hits observed
        best_agent, best_hits = max(scores.items(), key=lambda kv: kv[1])
        conf = best_hits / max(scores.values())
        sig = RouteSignal(source="keyword", agent=best_agent, confidence=float(conf), details={"scores": scores})
        return best_agent, float(conf), sig

# ---------------- Ensemble arbitration ----------------

@dataclass
class EnsembleConfig:
    kw_min: float = float(os.getenv("ROUTER_KW_MIN", "0.35"))
    sem_min: float = float(os.getenv("ROUTER_SEM_MIN", "0.55"))
    llm_min: float = float(os.getenv("ROUTER_LLM_MIN", "0.70"))
    final_min: float = float(os.getenv("ROUTER_FINAL_MIN", "0.65"))
    llm_wins_over_kw_by: float = float(os.getenv("ROUTER_LLM_WIN_DELTA", "0.15"))
    sem_wins_over_kw_by: float = float(os.getenv("ROUTER_SEM_WIN_DELTA", "0.10"))
    prefer_last_topic_window_sec: int = int(os.getenv("ROUTER_LAST_TOPIC_WINDOW", "900"))  # 15min

class EnsembleRouter:
    """
    Combines keyword, semantic, LLM-intent, and topic-shift signals into a single decision.
    - If topic shift detector says 'shift', we downweight 'continue' behavior.
    - If last topic is recent and LLM-intent is 'card_replacement', we favor card agent.
    """
    def __init__(self, kw: KeywordRouter, sem, llm_intent, topic_shift, cfg: EnsembleConfig | None = None):
        self.kw = kw
        self.sem = sem
        self.llm_intent = llm_intent
        self.topic_shift = topic_shift
        self.cfg = cfg or EnsembleConfig()

    def decide(self, turn: TurnInput, *, last_topic: Optional[str], last_topic_time: Optional[float],
               session_facts: Dict[str, Any] | None) -> RouterResult:
        signals: List[RouteSignal] = []

        # 1) Keyword
        try:
            kw_agent, kw_conf, kw_sig = self.kw.route(turn)
            signals.append(kw_sig)
        except Exception as e:
            log.error(f"keyword route error: {e}")
            kw_agent, kw_conf, kw_sig = None, 0.0, RouteSignal(source="keyword")

        # 2) Semantic
        try:
            sem_agent, sem_conf, sem_details = self.sem.route(turn.text or "")
            sem_sig = RouteSignal(source="semantic", agent=sem_agent, confidence=sem_conf, details=sem_details)
            signals.append(sem_sig)
        except Exception as e:
            log.error(f"semantic route error: {e}")
            sem_agent, sem_conf, sem_sig = None, 0.0, RouteSignal(source="semantic")

        # 3) LLM intent
        try:
            intent, llm_conf, slots = self.llm_intent.classify(
                user_text=turn.text or "",
                recent_messages=(turn.metadata or {}).get("recent_messages", []),
                session_facts=session_facts or {},
                last_topic=last_topic
            )
            # map intents -> agent names (keep centralized here)
            intent_map = {
                "card_block": "agent-card-control-llm",
                "card_replacement": "agent-card-control-llm",
                "appointment_booking": "agent-appointment-llm",
                "faq": "agent-faq-llm",
            }
            llm_agent = intent_map.get(intent)
            llm_sig = RouteSignal(source="llm", agent=llm_agent, confidence=llm_conf, details={"intent": intent, "slots": slots})
            signals.append(llm_sig)
        except Exception as e:
            log.error(f"llm intent error: {e}")
            llm_agent, llm_conf, llm_sig = None, 0.0, RouteSignal(source="llm")

        # 4) Topic shift
        try:
            is_shift, suggested_agent, shift_conf = self.topic_shift.detect(turn.text or "", last_topic)
            topic_sig = RouteSignal(source="topic", agent=suggested_agent if is_shift else None,
                                    confidence=shift_conf if is_shift else 0.0,
                                    details={"is_shift": is_shift})
            signals.append(topic_sig)
        except Exception as e:
            log.error(f"topic shift error: {e}")
            topic_sig = RouteSignal(source="topic", agent=None, confidence=0.0, details={"is_shift": False})

        # --- Policy: pick best among valid signals with simple tie-breakers ---
        picked_agent, picked_conf, picked_src = None, 0.0, None

        # Candidate list with minimums
        candidates: List[Tuple[str, float, str]] = []
        if kw_agent and kw_conf >= self.cfg.kw_min:
            candidates.append((kw_agent, kw_conf, "keyword"))
        if sem_agent and sem_conf >= self.cfg.sem_min:
            candidates.append((sem_agent, sem_conf, "semantic"))
        if llm_sig.agent and llm_conf >= self.cfg.llm_min:
            candidates.append((llm_sig.agent, llm_conf, "llm"))

        # Prefer LLM if it beats keyword by margin; prefer semantic over keyword by margin
        by_src: Dict[str, Tuple[str, float]] = {}
        for agent, conf, src in candidates:
            prev = by_src.get(agent)
            if (not prev) or (conf > prev[1]):
                by_src[agent] = (src, conf)

        # Flatten and choose best according to tie-breakers
        if by_src:
            # pick best confidence first
            agent, (src, conf) = max(by_src.items(), key=lambda kv: kv[1][1])
            picked_agent, picked_conf, picked_src = agent, conf, src

            # If keyword vs llm tie: apply deltas
            if picked_src == "keyword" and llm_sig.agent == picked_agent and llm_conf >= (kw_conf + self.cfg.llm_wins_over_kw_by):
                picked_agent, picked_conf, picked_src = llm_sig.agent, llm_conf, "llm"
            if picked_src == "keyword" and sem_agent == picked_agent and sem_conf >= (kw_conf + self.cfg.sem_wins_over_kw_by):
                picked_agent, picked_conf, picked_src = sem_agent, sem_conf, "semantic"

        # Bias by recent last_topic if not a shift and user intent is ambiguous smalltalk
        from time import time as _now
        if topic_sig.details.get("is_shift") is False and last_topic and last_topic_time:
            if (_now() - float(last_topic_time)) <= self.cfg.prefer_last_topic_window_sec:
                # If LLM intent matched same agent as last topic's natural owner, keep it
                # (you can inject your last_topic->agent mapping if needed)
                pass

        # If nothing strong enough, ask clarify
        if not picked_agent or picked_conf < self.cfg.final_min:
            question = "Could you clarify whether you want card help, an appointment, or an FAQ?"
            return RouterResult(agent="__clarify__", confidence=0.0,
                                clarify={"question": question}, signals=signals)

        log.info("route", extra={"stage": "router.pick", "agent": picked_agent, "conf": picked_conf, "src": picked_src})
        return RouterResult(agent=picked_agent, confidence=float(picked_conf), signals=signals)
