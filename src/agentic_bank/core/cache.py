import os, json, hashlib, time
from typing import Any, Optional

class InMemoryCache:
    def __init__(self): self._d = {}
    def get(self, k: str) -> Optional[Any]:
        v = self._d.get(k); 
        if not v: return None
        if v["exp"] and v["exp"] < time.time(): self._d.pop(k, None); return None
        return v["val"]
    def set(self, k: str, val: Any, ttl: int | None = None):
        self._d[k] = {"val": val, "exp": (time.time() + ttl) if ttl else None}

_cache = InMemoryCache()

try:
    import redis
    class RedisCache:
        def __init__(self, url: str):
            self.r = redis.from_url(url, decode_responses=True)
        def get(self, k: str):
            v = self.r.get(k); 
            return json.loads(v) if v else None
        def set(self, k: str, val: Any, ttl: int | None = None):
            self.r.set(k, json.dumps(val), ex=ttl if ttl else None)
except Exception:  # redis not installed
    RedisCache = None

def get_cache():
    url = os.getenv("REDIS_URL")
    if url and RedisCache:
        return RedisCache(url)
    return _cache

def make_key(prefix: str, payload: Any) -> str:
    s = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return prefix + ":" + hashlib.sha256(s.encode("utf-8")).hexdigest()
