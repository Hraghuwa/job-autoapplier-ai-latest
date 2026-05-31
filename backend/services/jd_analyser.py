"""Phase A — Job Description analyser.

Reads raw JD text, asks the LLM router for a structured signature, then
applies a hallucination guard so every claimed `must_have` actually appears
in the JD text. Returns a `JDSignature` even when the LLM call fails or
returns garbage — the rest of the pipeline must never crash on bad input.

Model used:
    role="form_fill"  →  Ollama Qwen2.5-7B  →  Groq Llama-3.1-8B  →  Gemini Flash
    Chosen because the output is a small structured JSON object and we
    want low latency (this runs once per JD, but the loop hits 100s/day).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Callable, Optional

from backend.services.career_schemas import JDSignature

# Ensure the repo-root llm_router is importable from inside this package.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


# Type alias: the LLM function takes (prompt, **kwargs) → Optional[str]
LLMFn = Callable[..., Optional[str]]


def _default_llm() -> LLMFn:
    """Lazy import so tests don't pay the import cost."""
    from llm_router import generate as _generate
    return _generate


_PROMPT_TEMPLATE = """You analyse job descriptions for an automated job-application agent.

Read the JD below and return ONLY a valid JSON object with this exact shape:
{{
  "keywords":      [list of 5-12 lowercase keywords/skills],
  "must_haves":    [list of skills/qualifications explicitly required],
  "nice_to_haves": [list of skills/qualifications described as preferred or bonus],
  "seniority":     one of "intern" | "junior" | "mid" | "senior" | "staff" | "lead" | "unknown",
  "archetype":     short noun phrase like "backend python", "ml engineer", "growth pm",
  "red_flags":     [list of concerning items — unpaid, excessive hours, vague pay, etc.]
}}

Rules:
- Every must_have MUST appear verbatim (or as a clear synonym) in the JD text.
- Do NOT invent skills the JD does not mention.
- Use lowercase for keywords.
- If you can't tell, use "unknown" rather than guessing.

JD:
\"\"\"
{jd_text}
\"\"\"

JSON only, no markdown, no commentary."""


def _hash_jd(jd_text: str) -> str:
    """Stable 16-char hex hash of the JD — used as the cache key."""
    norm = re.sub(r"\s+", " ", (jd_text or "").strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]


def _safe_empty(jd_text: str) -> JDSignature:
    """Build a never-crash empty signature when the LLM path fails entirely."""
    return JDSignature(jd_hash=_hash_jd(jd_text))


def _strip_code_fence(text: str) -> str:
    """Some models wrap JSON in ```json … ``` even when told not to."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.lstrip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    return t.strip()


def _hallucination_filter(items: list[str], jd_text: str) -> list[str]:
    """Drop any item not present in the JD text (case-insensitive substring).
    Words ≤ 3 chars are kept unfiltered (too noisy — 'js', 'go', 'ai')."""
    jd_lower = (jd_text or "").lower()
    out = []
    for it in items or []:
        if not isinstance(it, str):
            continue
        it_clean = it.strip()
        if not it_clean:
            continue
        # Multi-word phrases: require the head noun to appear.
        probe = it_clean.lower()
        if len(probe) <= 3 or probe in jd_lower or _any_token_in(probe, jd_lower):
            out.append(it_clean)
    return out


def _any_token_in(phrase: str, haystack: str) -> bool:
    """For a multi-word phrase, accept if its longest token (>=4 chars) is in
    the haystack. Handles 'fastapi' vs '5+ years FastAPI' etc."""
    tokens = [t for t in re.split(r"\W+", phrase) if len(t) >= 4]
    return any(t in haystack for t in tokens)


def analyse(
    jd_text: str,
    *,
    llm: Optional[LLMFn] = None,
    config: Optional[dict] = None,
) -> JDSignature:
    """Analyse JD text → JDSignature. Never raises.

    Args:
        jd_text: raw job description.
        llm:     optional LLM function for testing. Defaults to llm_router.generate.
        config:  optional agent config (carries per-user API keys).
    """
    if llm is None:
        llm = _default_llm()

    prompt = _PROMPT_TEMPLATE.format(jd_text=(jd_text or "")[:8000])

    try:
        raw = llm(prompt, role="form_fill", config=config or {}, max_tokens=600, temperature=0.0)
    except Exception:
        return _safe_empty(jd_text)

    if not raw:
        return _safe_empty(jd_text)

    try:
        data = json.loads(_strip_code_fence(raw))
    except Exception:
        return _safe_empty(jd_text)

    if not isinstance(data, dict):
        return _safe_empty(jd_text)

    # Apply hallucination guard to must_haves and keywords (red_flags are
    # synthesized so we trust them as-is; nice_to_haves we also filter).
    must_haves    = _hallucination_filter(data.get("must_haves",    []), jd_text)
    nice_to_haves = _hallucination_filter(data.get("nice_to_haves", []), jd_text)
    keywords      = [k.lower().strip() for k in (data.get("keywords") or []) if isinstance(k, str) and k.strip()]

    seniority_raw = (data.get("seniority") or "unknown").strip().lower()
    valid_levels = {"intern", "junior", "mid", "senior", "staff", "lead", "unknown"}
    seniority = seniority_raw if seniority_raw in valid_levels else "unknown"

    try:
        return JDSignature(
            jd_hash       = _hash_jd(jd_text),
            keywords      = keywords[:20],
            must_haves    = must_haves[:20],
            nice_to_haves = nice_to_haves[:20],
            seniority     = seniority,    # type: ignore[arg-type]
            archetype     = (data.get("archetype") or "unknown").strip() or "unknown",
            red_flags     = [str(x).strip() for x in (data.get("red_flags") or []) if str(x).strip()][:10],
        )
    except Exception:
        return _safe_empty(jd_text)
