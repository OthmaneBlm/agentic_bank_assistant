from typing import Dict, Any

class InMemoryStore:
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def session(self, session_id: str) -> Dict[str, Any]:
        return self._sessions.setdefault(session_id, {})