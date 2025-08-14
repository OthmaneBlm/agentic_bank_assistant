import logging, os, sys, json, time
from typing import Any, Dict

def _json_fmt(record: logging.LogRecord) -> str:
    payload: Dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
        "lvl": record.levelname,
        "logger": record.name,
        "msg": record.getMessage(),
    }
    # include extras if present
    for k in ("turnId","sessionId","agent","conf","stage","tool","status"):
        v = getattr(record, k, None)
        if v is not None:
            payload[k] = v
    return json.dumps(payload, ensure_ascii=False)

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return _json_fmt(record)

def setup_logging():
    lvl = os.getenv("APP_LOG_LEVEL","INFO").upper()
    root = logging.getLogger()
    root.setLevel(lvl)
    # avoid duplicate handlers
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(JsonFormatter())
        root.addHandler(h)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
