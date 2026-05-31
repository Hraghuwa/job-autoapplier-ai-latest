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
        "groq":   os.environ.get("GROQ_FORM_MODEL",   "llama-3.1-8b-instant"),
        "gemini": os.environ.get("GEMINI_FORM_MODEL", "gemini-2.0-flash"),
    },
    "writer": {
        "ollama": os.environ.get("OLLAMA_WRITER_MODEL", "qwen2.5:14b-instruct"),
        "groq":   os.environ.get("GROQ_WRITER_MODEL",   "llama-3.3-70b-versatile"),
        "gemini": os.environ.get("GEMINI_WRITER_MODEL", "gemini-2.0-flash"),
    },
}

# Per-role provider priority. Tweak via JOBAGENT_LLM_ORDER="groq,gemini" if you
# want to skip the local model in CI.
DEFAULT_ORDER = {
    "form_fill": ("ollama", "groq", "gemini"),
    "writer":    ("ollama", "gemini", "groq"),  # writer prefers quality over speed
}

_ollama_alive_cache: Optional[bool] = None
_groq_client = None
_gemini_client = None


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
    except Exception:
        return None


def _call_groq(model: str, prompt: str, max_tokens: int, temperature: float, api_key: str) -> Optional[str]:
    global _groq_client
    try:
        if _groq_client is None:
            from groq import Groq
            _groq_client = Groq(api_key=api_key)
        resp = _groq_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception:
        _groq_client = None
        return None


def _call_gemini(model: str, prompt: str, api_key: str) -> Optional[str]:
    global _gemini_client
    try:
        if _gemini_client is None:
            from google import genai
            _gemini_client = genai.Client(api_key=api_key)
        resp = _gemini_client.models.generate_content(model=model, contents=prompt)
        text = (resp.text or "").strip()
        return text or None
    except Exception:
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
    config = config or {}
    groq_key   = config.get("groq_api_key", "")   or os.environ.get("GROQ_API_KEY", "")
    gemini_key = config.get("gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", "")

    # Sensible defaults per role; callers can override.
    if max_tokens is None:
        max_tokens = 200 if role == "form_fill" else 1200
    if temperature is None:
        temperature = 0.1 if role == "form_fill" else 0.4

    order_str = os.environ.get("JOBAGENT_LLM_ORDER")
    order = tuple(order_str.split(",")) if order_str else DEFAULT_ORDER[role]
    models = MODELS[role]

    for provider in order:
        if provider == "ollama":
            if not _ollama_reachable():
                continue
            out = _call_ollama(models["ollama"], prompt, max_tokens, temperature)
            if out:
                return out
        elif provider == "groq":
            if not groq_key:
                continue
            out = _call_groq(models["groq"], prompt, max_tokens, temperature, groq_key)
            if out:
                return out
        elif provider == "gemini":
            if not gemini_key:
                continue
            out = _call_gemini(models["gemini"], prompt, gemini_key)
            if out:
                return out

    return None


def reset_clients() -> None:
    """Drop cached clients — useful when a user rotates their API key mid-process."""
    global _groq_client, _gemini_client, _ollama_alive_cache
    _groq_client = None
    _gemini_client = None
    _ollama_alive_cache = None
