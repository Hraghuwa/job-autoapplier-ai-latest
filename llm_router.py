"""Unified LLM router for JobAgent.

Two roles, two model tiers each, with automatic fallback:

  role="form_fill"   short, structured, low-latency (Ollama Qwen2.5-7B → Groq llama-3.1-8b → Gemini Flash)
  role="writer"      longer prose, careful rewrites    (Ollama Qwen2.5-14B → Gemini 1.5/2.0 Flash)

Why this exists:
  - Before this, _ask_ai was duplicated across linkedin_applier, wellfound_applier,
    and the agents/ copies — each with its own provider priority + client caching.
  - Resume tailoring went straight to Gemini Flash with no local-first option.
  - There was no way to A/B a local model without forking five files.

Routing rule:
  1. Try Ollama if OLLAMA_HOST is reachable (LOCAL, free, private).
  2. Try Groq for form_fill (cloud, fast, cheap).
  3. Try Gemini for writer (cloud, quality).
  4. Return None and let the caller fall back to autofill_bank / skip.

The router never raises — providers that fail are skipped and the next tier is
tried. Callers MUST tolerate `None` (form_fill) or "" (writer) returns.
"""
from __future__ import annotations

import os
from typing import Optional, Literal

Role = Literal["form_fill", "writer"]

# Provider priority per role. Models can be overridden via env vars so you can
# swap (e.g. Qwen2.5-Math-7B) without code changes.
MODELS = {
    "form_fill": {
        "ollama": os.environ.get("OLLAMA_FORM_MODEL", "qwen2.5:7b-instruct"),
        "groq":   os.environ.get("GROQ_FORM_MODEL",   "openai/gpt-oss-20b"),
        "gemini": os.environ.get("GEMINI_FORM_MODEL", "gemini-2.5-flash"),
    },
    "writer": {
        "ollama": os.environ.get("OLLAMA_WRITER_MODEL", "qwen2.5:14b-instruct"),
        "groq":   os.environ.get("GROQ_WRITER_MODEL",   "openai/gpt-oss-120b"),
        "gemini": os.environ.get("GEMINI_WRITER_MODEL", "gemini-2.5-flash"),
    },
}

# Per-role provider priority. Tweak via JOBAGENT_LLM_ORDER="groq,gemini" if you
# want to skip the local model in CI.
DEFAULT_ORDER = {
    "form_fill": ("ollama", "groq", "gemini"),
    "writer":    ("ollama", "gemini", "groq"),  # writer prefers quality over speed
}

_ollama_alive_cache: Optional[bool] = None
_groq_clients: dict = {}    # keyed by api key — per-user keys must not share a client
_gemini_clients: dict = {}
LAST_ERROR: Optional[str] = None  # last provider failure, so callers can say why generate() returned None


def _note_error(provider: str, e: Exception) -> None:
    global LAST_ERROR
    msg = str(e)
    if "API_KEY_INVALID" in msg or "API key not valid" in msg:
        msg = "API key not valid"
    LAST_ERROR = f"{provider}: {type(e).__name__}: {msg[:160]}"


def _ollama_reachable() -> bool:
    """Cache a single probe per process — avoids hammering localhost on every field."""
    global _ollama_alive_cache
    if _ollama_alive_cache is not None:
        return _ollama_alive_cache
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    try:
        import urllib.request
        req = urllib.request.Request(host + "/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=0.6):
            _ollama_alive_cache = True
    except Exception:
        _ollama_alive_cache = False
    return _ollama_alive_cache


def _call_ollama(model: str, prompt: str, max_tokens: int, temperature: float) -> Optional[str]:
    try:
        import urllib.request
        import json
        host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        body = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        }).encode()
        req = urllib.request.Request(
            host + "/api/generate", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return (data.get("response") or "").strip() or None
    except Exception as e:
        _note_error("ollama", e)
        return None


def _call_groq(model: str, prompt: str, max_tokens: int, temperature: float, api_key: str) -> Optional[str]:
    try:
        client = _groq_clients.get(api_key)
        if client is None:
            from groq import Groq
            client = _groq_clients[api_key] = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception as e:
        _groq_clients.pop(api_key, None)
        _note_error("groq", e)
        return None


def _call_gemini(model: str, prompt: str, api_key: str) -> Optional[str]:
    try:
        client = _gemini_clients.get(api_key)
        if client is None:
            from google import genai
            client = _gemini_clients[api_key] = genai.Client(api_key=api_key)
        resp = client.models.generate_content(model=model, contents=prompt)
        text = (resp.text or "").strip()
        return text or None
    except Exception as e:
        _note_error("gemini", e)
        # google-generativeai legacy path
        try:
            import google.generativeai as legacy
            legacy.configure(api_key=api_key)
            m = legacy.GenerativeModel(model)
            r = m.generate_content(prompt)
            return (r.text or "").strip() or None
        except Exception:
            return None


def generate(
    prompt: str,
    *,
    role: Role = "form_fill",
    config: Optional[dict] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Optional[str]:
    """Run `prompt` through the role-appropriate provider chain.

    Returns the trimmed text, or None if every provider failed / no keys
    configured. Never raises.

    `config` is the agent CONFIG dict (carries per-user groq_api_key /
    gemini_api_key). Env vars are the fallback.
    """
    global LAST_ERROR
    config = config or {}
    if config.get("_llm_disabled"):
        # The worker sets this when the user has no own key and no AI tokens
        # left: the pipeline falls back to its non-AI paths instead of spending
        # the operator's keys.
        LAST_ERROR = "AI disabled for this run (token balance exhausted — add your own key)"
        return None
    groq_key   = config.get("groq_api_key", "")   or os.environ.get("GROQ_API_KEY", "")
    gemini_key = config.get("gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")
    own = {"groq": bool(config.get("groq_api_key")), "gemini": bool(config.get("gemini_api_key"))}

    # Sensible defaults per role; callers can override.
    if max_tokens is None:
        max_tokens = 200 if role == "form_fill" else 1200
    if temperature is None:
        temperature = 0.1 if role == "form_fill" else 0.4

    order_str = os.environ.get("JOBAGENT_LLM_ORDER")
    order = tuple(order_str.split(",")) if order_str else DEFAULT_ORDER[role]
    models = MODELS[role]

    import time as _time
    started = _time.time()
    user_id = config.get("user_id")

    for provider in order:
        if provider == "ollama":
            if not _ollama_reachable():
                continue
            out = _call_ollama(models["ollama"], prompt, max_tokens, temperature)
        elif provider == "groq":
            if not groq_key:
                continue
            out = _call_groq(models["groq"], prompt, max_tokens, temperature, groq_key)
        elif provider == "gemini":
            if not gemini_key:
                continue
            out = _call_gemini(models["gemini"], prompt, gemini_key)
        else:
            continue

        if out:
            # Observability: record token/cost estimates to ai_requests.
            # Best-effort and isolated — a broken sink must never break the
            # apply pipeline (see backend/services/llm_usage.py).
            try:
                _record_usage_safe(
                    provider=provider,
                    model=models[provider],
                    role=role,
                    prompt_tokens=_estimate_tokens(prompt),
                    output_tokens=_estimate_tokens(out),
                    latency_ms=int((_time.time() - started) * 1000),
                    user_id=str(user_id) if user_id else None,
                    run_id=config.get("run_id"),
                    billed_to=("local" if provider == "ollama"
                               else "user" if own.get(provider) else "operator"),
                )
            except Exception:
                pass
            return out

    return None


def _estimate_tokens(text: Optional[str]) -> int:
    """~4 chars/token; kept local so the CLI works without the backend package."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _record_usage_safe(**kwargs) -> bool:
    """Forward to backend.services.llm_usage.record_usage when the backend
    package is importable (server/worker/subprocess); silently no-op for the
    standalone CLI. Module-level so tests can monkeypatch it."""
    try:
        from backend.services.llm_usage import record_usage
        return record_usage(**kwargs)
    except Exception:
        return False


def reset_clients() -> None:
    """Drop cached clients — useful when a user rotates their API key mid-process."""
    global _ollama_alive_cache
    _groq_clients.clear()
    _gemini_clients.clear()
    _ollama_alive_cache = None
