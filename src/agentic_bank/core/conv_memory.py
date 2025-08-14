"""
This is a simple file-based memory for dev. You can swap to Redis/Postgres later.
"""
from typing import List, Dict, Any
import time, json
from pathlib import Path

class ConversationMemory:
    """Append-only light memory per (userId, sessionId)."""
    def __init__(self, base: Path):
        self.base = base; self.base.mkdir(parents=True, exist_ok=True)

    def _fp(self, user_id: str, session_id: str) -> Path:
        return self.base / f"{user_id}__{session_id}.jsonl"

    def append(self, user_id: str, session_id: str, role: str, content: str, meta: Dict[str, Any] | None = None):
        rec = {"ts": time.time(), "role": role, "content": content, "meta": meta or {}}
        self._fp(user_id, session_id).open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")

    def last_n(self, user_id: str, session_id: str, n: int = 20) -> List[Dict[str, Any]]:
        fp = self._fp(user_id, session_id)
        if not fp.exists(): return []
        lines = fp.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(x) for x in lines]
