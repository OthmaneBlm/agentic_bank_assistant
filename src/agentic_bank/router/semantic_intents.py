from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field
import math
import os
from openai import AzureOpenAI
from agentic_bank.core.logging import get_logger

log = get_logger("router.semantic")


@dataclass
class Intent:
    agent: str
    examples: List[str]
    vecs: List[List[float]] = field(default_factory=list)


class SemanticIntents:
    """
    Simple centroid similarity over few-shot examples per agent.
    Configure your deployment name for embeddings in Azure OpenAI.
    """

    def __init__(self, intents: List[Intent] | None = None, threshold: float = 0.55):
        self.threshold = threshold

        # Initialize Azure OpenAI client
        self.client = AzureOpenAI(
            api_version="2024-12-01-preview",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_KEY")
        )

        # Replace with your Azure OpenAI embeddings deployment name
        self.embed_model = os.getenv("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT", "text-embedding-3-large")

        # Default intents if none provided
        self.intents = intents or [
            Intent("agent-card-control-llm", [
                "my card is lost", "stolen card", "block my card",
                "freeze my card", "fraud on my card",
                "order a replacement", "order a new one"
            ]),
            Intent("agent-appointment-llm", [
                "book an appointment", "schedule a meeting",
                "branch visit tomorrow", "set up a visit", "book a slot"
            ]),
            Intent("agent-faq-llm", [
                "what is atm limit", "how much can I withdraw",
                "transfer cutoff time", "fees and limits"
            ]),
        ]

        # Precompute embeddings for each intent
        self._initialize_intent_embeddings()

    def _initialize_intent_embeddings(self) -> None:
        for intent in self.intents:
            intent.vecs = self._batch_embed(intent.examples)

    def _embed(self, text: str) -> List[float]:
        """Embed a single string."""
        response = self.client.embeddings.create(
            input=text,
            model=self.embed_model,
        )
        return response.data[0].embedding

    def _batch_embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of strings."""
        response = self.client.embeddings.create(
            input=texts,
            model=self.embed_model,
        )
        return [item.embedding for item in response.data]

    @staticmethod
    def _cos(u: List[float], v: List[float]) -> float:
        num = sum(a * b for a, b in zip(u, v))
        du = math.sqrt(sum(a * a for a in u)) + 1e-9
        dv = math.sqrt(sum(b * b for b in v)) + 1e-9
        return max(min(num / (du * dv), 1.0), -1.0)

    def route(self, text: str) -> Tuple[Optional[str], float, Dict[str, Any]]:
        """Route an input text to the most likely agent intent."""
        if not text:
            return None, 0.0, {"scores": {}}

        q = self._embed(text)
        scores = {
            intent.agent: max((self._cos(q, v) for v in intent.vecs), default=0.0)
            for intent in self.intents
        }

        agent, conf = max(scores.items(), key=lambda kv: kv[1])
        if conf < self.threshold:
            return None, conf, {"scores": scores}
        return agent, conf, {"scores": scores}
