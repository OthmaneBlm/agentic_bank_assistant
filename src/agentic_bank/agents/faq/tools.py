import os
from typing import Dict, Any, List, Tuple
import numpy as np
from pathlib import Path

from agentic_bank.core.tooling import Tool, ToolRegistry
from agentic_bank.core.llm.embeddings import embed_texts, cosine_sim_matrix

DATA_DIR = Path(__file__).resolve().parents[2].parents[1] / "data" / "faq"

_DOCS: List[Tuple[str, str]] = []
for p in sorted(DATA_DIR.glob("*.md")):
    _DOCS.append((p.stem, p.read_text(encoding="utf-8").strip()))

_USE_EMB = os.getenv("RAG_USE_EMBEDDINGS","false").lower() == "true"
_EMB = None
if _USE_EMB and _DOCS:
    try:
        _EMB = embed_texts([t for _, t in _DOCS])
    except Exception:
        _USE_EMB = False

def _keyword_search(query: str, k: int = 3) -> List[Dict[str, Any]]:
    q = (query or "").lower()
    scored = []
    for doc_id, text in _DOCS:
        score = sum(1 for w in q.split() if w in text.lower())
        if score > 0:
            scored.append((score, doc_id, text))
    scored.sort(reverse=True)
    top = scored[:k] if scored else [(1, _DOCS[0][0], _DOCS[0][1])] if _DOCS else []
    return [{"id": d, "passage": t} for _, d, t in top]

def _vector_search(query: str, k: int = 3) -> List[Dict[str, Any]]:
    if not _DOCS:
        return []
    qv = embed_texts([query])
    sims = cosine_sim_matrix(qv, _EMB)
    order = np.argsort(-sims[0])[:k]
    return [{"id": _DOCS[i][0], "passage": _DOCS[i][1]} for i in order]

def register_faq_tools(registry: ToolRegistry):
    def retrieve(args: Dict[str, Any]):
        query = args.get("query","")
        if _USE_EMB and _EMB is not None:
            passages = _vector_search(query)
        else:
            passages = _keyword_search(query)
        return {"passages": passages}
    registry.register(Tool("knowledge.retrieve", retrieve, "Retrieve FAQ passages"))