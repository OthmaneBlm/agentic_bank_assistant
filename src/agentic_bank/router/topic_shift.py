from __future__ import annotations
from typing import Tuple, Optional, Dict, List
import math
import os
from agentic_bank.core.llm.azure import AzureOpenAI
from agentic_bank.core.logging import get_logger

log = get_logger("router.topic")


class TopicShiftDetector:
    """
    Lightweight topic shift detection: compare embedding of current text
    with a centroid (embedding) for the last_topic label.
    """

    def __init__(self, threshold: float = 0.50):
        self.client = AzureOpenAI(
            api_version="2024-12-01-preview",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        )
        self.threshold = threshold

        # Naive exemplars; adjust to your topics
        self.topic_exemplars: Dict[str, str] = {
            "card_block": "block or freeze a payment card due to lost stolen or fraud",
            "appointment": "book or schedule a branch appointment",
            "faq": "ask general banking information limits fees rates",
        }

        # Cache for exemplar embeddings and runtime embeddings
        self._cache: Dict[str, List[float]] = {}

        # Precompute all exemplar embeddings
        for topic, exemplar in self.topic_exemplars.items():
            self._cache[topic] = self._embed_text(exemplar)

    def _embed_text(self, text: str) -> List[float]:
        """Embed a single text via Azure OpenAI embeddings."""
        response = self.client.embeddings.create(
            model="text-embedding-ada-002",  # replace with your deployment name
            input=[text],
        )
        return response.data[0].embedding

    @staticmethod
    def _cos(u: List[float], v: List[float]) -> float:
        """Cosine similarity between two vectors."""
        num = sum(a * b for a, b in zip(u, v))
        du = math.sqrt(sum(a * a for a in u)) + 1e-9
        dv = math.sqrt(sum(b * b for b in v)) + 1e-9
        return max(min(num / (du * dv), 1.0), -1.0)

    def detect(self, text: str, last_topic: Optional[str]) -> Tuple[bool, Optional[str], float]:
        if not last_topic or not text:
            return False, None, 0.0

        # Get exemplar vector for last_topic
        ex_vec = self._cache.get(last_topic)
        if not ex_vec:
            return False, None, 0.0

        # Embed current text (cache if repeated text seen)
        if text not in self._cache:
            self._cache[text] = self._embed_text(text)
        cur_vec = self._cache[text]

        # Check similarity to last topic
        sim = self._cos(ex_vec, cur_vec)
        is_shift = sim < self.threshold

        # Optional suggestion: find closest other topic exemplar
        best_topic, best_sim = None, -1.0
        for topic, exemplar_vec in self._cache.items():
            if topic == last_topic or topic not in self.topic_exemplars:
                continue
            s = self._cos(exemplar_vec, cur_vec)
            if s > best_sim:
                best_topic, best_sim = topic, s

        suggested_agent = {
            "card_block": "agent-card-control-llm",
            "appointment": "agent-appointment-llm",
            "faq": "agent-faq-llm",
        }.get(best_topic)

        log.info(
            "topic",
            extra={
                "stage": "router.topic",
                "last_topic": last_topic,
                "sim": sim,
                "shift": is_shift,
                "suggest": best_topic,
                "sugg_sim": best_sim,
            },
        )

        return is_shift, suggested_agent, float(1.0 - sim)
