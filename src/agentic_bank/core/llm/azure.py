import os, json as _json
from typing import List, Dict, Any, Optional, Tuple
from openai import AzureOpenAI
from agentic_bank.core.logging import get_logger
from agentic_bank.core.cache import get_cache, make_key

_log = get_logger("llm.azure")

class AzureLLM:
    def __init__(self):
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION","2024-08-01-preview")
        self.cache = get_cache()
        self.cache_ttl = int(os.getenv("LLM_CACHE_TTL_SECONDS", "120"))  # 2 min default

        if not endpoint or not api_key:
            raise RuntimeError("Missing Azure OpenAI env vars")
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        if not self.deployment:
            raise RuntimeError("Set AZURE_OPENAI_DEPLOYMENT")
        self.client = AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)

    def chat(self, messages: List[Dict[str, str]], system: Optional[str] = None, json_mode: bool = False) -> str:
        msgs = []
        if system:
            msgs.append({"role":"system","content":system})
        msgs.extend(messages)
        kwargs: Dict[str, Any] = {}
        if json_mode:
            kwargs["response_format"] = {"type":"json_object"}
        resp = self.client.chat.completions.create(
            model=self.deployment,
            messages=msgs,
            temperature=0.2,
            **kwargs
        )
        return resp.choices[0].message.content or ""

    def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        *,
        tools: List[Dict[str, Any]],
        system: Optional[str] = None,
        max_iters: int = 4,
        tool_executor=None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        # Build a stable cache key (no tool results, just input)
        ckey = make_key("chat_with_tools", {
            "deployment": self.deployment,
            "system": system,
            "messages": messages,
            "tools": tools,
        })
        cached = self.cache.get(ckey)
        if cached:
            # Return cached assistant text only (no summaries since no tool exec)
            return cached["text"], cached.get("summaries", [])
        
        msgs: List[Dict[str, Any]] = []
        
        if system:
            msgs.append({"role":"system","content":system})
        msgs.extend(messages)
        summaries: List[Dict[str, Any]] = []
        
        for _ in range(max_iters):
            resp = self.client.chat.completions.create(
                model=self.deployment,
                messages=msgs,
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
            )
            msg = resp.choices[0].message
            if not getattr(msg, "tool_calls", None):
                _log.debug("assistant text", extra={"stage":"llm.reply"})
                text = msg.content or ""
                if self.cache_ttl > 0 and text:
                    self.cache.set(ckey, {"text": text, "summaries": summaries}, ttl=self.cache_ttl)
                return text, summaries
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                _log.info("llm tool_call", extra={"stage":"llm.tc", "tool":fn_name})
                try:
                    args = _json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                status, data = ("error", {"message":"no executor"})
                if tool_executor is not None:
                    tool_id = fn_name.replace("_", ".", 1)
                    status, data = tool_executor.call(tool_id, args)
                summaries.append({"name": fn_name, "arguments": args, "status": status, "data": data})
                _log.info("llm tool_result", extra={"stage":"llm.tc.result", "tool":fn_name, "status":status})
                msgs.append({
                    "role":"assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": fn_name, "arguments": tc.function.arguments},
                    }],
                })
                msgs.append({
                    "role":"tool",
                    "tool_call_id": tc.id,
                    "name": fn_name,
                    "content": _json.dumps(data),
                })
        _log.error("max iters hit", extra={"stage":"llm.error"})
        return ("Sorry, I couldn't complete the request right now.", summaries)