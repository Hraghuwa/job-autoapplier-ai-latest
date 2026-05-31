"""Tests for backend.services.resume_pdf — Phase C.

Contract:
    resume_pdf.render(tailored_resume) -> bytes  # PDF bytes
    resume_pdf.render_to_path(tailored_resume, path) -> str  # returns path

Guarantees:
    1. Output is a valid PDF (starts with %PDF-).
    2. Text is selectable (round-trippable via pdftotext or PyPDF2).
    3. Every kept bullet text appears in the rendered text.
    4. File size < 200 KB for a normal-sized resume.
    5. Header (name, email) is in the rendered text.
    6. Determinism — same input twice produces text-equal PDFs.
"""
from __future__ import annotations

import os
import tempfile

import pytest

from backend.services import resume_pdf
from backend.services.career_schemas import (
    JDSignature, TailoredBullet, TailoredExperience, TailoredResume,
)


def _sample_tailored() -> TailoredResume:
    return TailoredResume(
        name="Harsh Raghuwanshi",
        email="h@example.com",
        phone="+91-9999999999",
        location="Bengaluru, IN",
        summary="Backend engineer focused on FastAPI and Postgres.",
        skills=["python", "fastapi", "postgres"],
        experience=[
            TailoredExperience(
                company="Acme", role="Software Engineer",
                bullets=[
                    TailoredBullet(id="b1",
                                   text="Built FastAPI service serving 5k RPS.",
                                   evidence_in_profile="b1",
                                   keywords_hit=["python", "fastapi"]),
                    TailoredBullet(id="b2",
                                   text="Owned Postgres migrations across 12 production DBs.",
                                   evidence_in_profile="b2",
                                   keywords_hit=["postgres"]),
                ],
            )
        ],
        education=["B.Tech CSE, Acme Univ, 2024"],
        keywords_added=["python", "fastapi", "postgres"],
        jd_coverage=0.75,
    )


def _pdf_to_text(pdf_bytes: bytes) -> str:
    """Extract text using PyPDF2 — that's the most ATS-like behavior we can
    test in-process. Returns concatenated text from all pages."""
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # legacy fallback
        except ImportError:
            pytest.skip("pypdf/PyPDF2 not installed")
    import io
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(p.extract_text() or "" for p in reader.pages)


# ── RED 1: render returns valid PDF bytes ───────────────────────────────────
def test_render_returns_valid_pdf_bytes():
    pdf = resume_pdf.render(_sample_tailored())
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-"), f"Not a PDF: starts with {pdf[:8]!r}"


# ── RED 2: header (name + email) is in the rendered text ────────────────────
def test_header_appears_in_rendered_text():
    pdf = resume_pdf.render(_sample_tailored())
    text = _pdf_to_text(pdf)
    assert "Harsh" in text
    assert "h@example.com" in text


# ── RED 3: every kept bullet text appears in the rendered text ──────────────
def test_every_bullet_is_rendered():
    tr = _sample_tailored()
    pdf = resume_pdf.render(tr)
    text = _pdf_to_text(pdf)
    for exp in tr.experience:
        for b in exp.bullets:
            # Allow soft hyphenation / linebreak — check first 5 words.
            head = " ".join(b.text.split()[:5])
            assert head in text, f"Bullet not in PDF: {head!r}"


# ── RED 4: file size sanity check (<200 KB) ─────────────────────────────────
def test_pdf_is_under_200kb():
    pdf = resume_pdf.render(_sample_tailored())
    assert len(pdf) < 200 * 1024, f"PDF too large: {len(pdf)} bytes"


# ── RED 5: render_to_path writes the file and returns the path ──────────────
def test_render_to_path_writes_file():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "out.pdf")
        returned = resume_pdf.render_to_path(_sample_tailored(), path)
        assert returned == path
        assert os.path.exists(path)
        with open(path, "rb") as f:
            assert f.read(4) == b"%PDF"


# ── RED 6: rendering an empty resume doesn't crash ──────────────────────────
def test_empty_resume_does_not_crash():
    tr = TailoredResume(name="X", email="x@x", summary="")
    pdf = resume_pdf.render(tr)
    assert pdf.startswith(b"%PDF-")
