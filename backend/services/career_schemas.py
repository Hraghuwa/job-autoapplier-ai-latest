"""Pydantic contracts shared across the JD → tailored-PDF → apply pipeline.

These are pure data shapes — no behavior. They form the locked interface
between Phase A (jd_analyser), Phase B (resume_tailor), and Phase C
(resume_pdf), so each phase can be built and tested in isolation.
"""
from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

Seniority = Literal["unknown", "intern", "junior", "mid", "senior", "staff", "lead"]


class JDSignature(BaseModel):
    """Structured analysis of a single job description (Phase A output)."""
    jd_hash:        str
    keywords:       List[str] = Field(default_factory=list)
    must_haves:     List[str] = Field(default_factory=list)
    nice_to_haves:  List[str] = Field(default_factory=list)
    seniority:      Seniority = "unknown"
    archetype:      str       = "unknown"
    red_flags:      List[str] = Field(default_factory=list)


class TailoredBullet(BaseModel):
    """A single rewritten bullet, traceable back to its source in the profile."""
    id:                   str
    text:                 str
    evidence_in_profile:  str            # ID of the source bullet/role in profile
    keywords_hit:         List[str] = Field(default_factory=list)


class TailoredExperience(BaseModel):
    company: str
    role:    str
    bullets: List[TailoredBullet] = Field(default_factory=list)


class TailoredResume(BaseModel):
    """Phase B output. The hallucination guard runs in Phase B and any bullet
    whose `evidence_in_profile` does not resolve in the source profile is
    dropped before construction — so by the time this model exists, it is
    safe to render to PDF in Phase C."""
    name:             str
    email:            str
    phone:            Optional[str]            = None
    location:         Optional[str]            = None
    summary:          str
    skills:           List[str]                = Field(default_factory=list)
    experience:       List[TailoredExperience] = Field(default_factory=list)
    education:        List[str]                = Field(default_factory=list)
    keywords_added:   List[str]                = Field(default_factory=list)
    jd_coverage:      float                    = 0.0   # 0..1 fraction of must_haves hit
    dropped_bullets:  List[str]                = Field(default_factory=list)  # IDs dropped by guard
