from pydantic import BaseModel
from typing import Optional, Dict, Any
import os, json
from pathlib import Path

class UserProfile(BaseModel):
    userId: str
    fullName: Optional[str] = None
    preferredLocale: Optional[str] = None
    tier: Optional[str] = None         # e.g., "standard", "premium"
    lastSeenAt: Optional[str] = None
    attributes: Dict[str, Any] = {}

class ProfileStore:
    """Minimal pluggable store. Defaults to JSON files under data/profiles/."""
    def __init__(self, base: Path):
        self.base = base
        self.base.mkdir(parents=True, exist_ok=True)

    def load(self, user_id: str) -> UserProfile:
        p = self.base / f"{user_id}.json"
        if not p.exists():
            return UserProfile(userId=user_id)
        return UserProfile(**json.loads(p.read_text(encoding="utf-8")))

    def save(self, profile: UserProfile):
        p = self.base / f"{profile.userId}.json"
        p.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
