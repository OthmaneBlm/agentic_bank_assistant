import re
from typing import Final

_ACK_PATTERNS: Final[list[re.Pattern]] = [
    re.compile(r"^\s*(yes|yep|yeah|y|ok|okay|k|fine|great|good|perfect)\.?\s*$", re.I),
    re.compile(r"^\s*(thanks|thank you|thx|cheers)\.?\s*$", re.I),
    re.compile(r"^\s*(no that'?s all|that'?s all|all good|all set|done|solved|resolved)\.?\s*$", re.I),
    re.compile(r"^\s*(bye|goodbye|see ya|see you)\.?\s*$", re.I),
]

def is_acknowledgement(text: str) -> bool:
    if not text:
        return False
    for pat in _ACK_PATTERNS:
        if pat.match(text):
            return True
    lowered = text.strip().lower()
    if len(lowered.split()) <= 6 and any(w in lowered for w in ["solved","resolved","close","closing","done","fixed"]):
        return True
    return False
