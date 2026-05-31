"""Phase C — ATS-safe PDF renderer.

Deterministic ReportLab template that produces a single-column, all-text
PDF that ATS parsers can read cleanly. No images, no fancy fonts, no tables —
just `<h1>name</h1>`-equivalent flowables and bullets.

The PDF embeds metadata (`/Title`, `/Keywords`) so even sloppy ATS scrapers
that read PDF metadata pick up the JD keywords.

Design rules (enforced by tests):
    - selectable text (real Tx glyphs, not raster)
    - file size < 200 KB for typical resumes
    - single column, A4
    - Helvetica only (universally available)
    - 18 mm margins, 10.5 pt body
"""
from __future__ import annotations

import io
import os
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem,
)

from backend.services.career_schemas import TailoredResume


# ── Styles ──────────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    name = ParagraphStyle(
        "ResumeName", parent=base["Title"],
        fontName="Helvetica-Bold", fontSize=18, leading=22, spaceAfter=2,
    )
    contact = ParagraphStyle(
        "ResumeContact", parent=base["Normal"],
        fontName="Helvetica", fontSize=9, leading=11, textColor="#555555",
        spaceAfter=8,
    )
    section = ParagraphStyle(
        "ResumeSection", parent=base["Heading2"],
        fontName="Helvetica-Bold", fontSize=11, leading=14,
        spaceBefore=10, spaceAfter=4, textColor="#222222",
    )
    body = ParagraphStyle(
        "ResumeBody", parent=base["Normal"],
        fontName="Helvetica", fontSize=10.5, leading=13,
    )
    role = ParagraphStyle(
        "ResumeRole", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=10.5, leading=13,
        spaceBefore=4, spaceAfter=2,
    )
    bullet = ParagraphStyle(
        "ResumeBullet", parent=base["Normal"],
        fontName="Helvetica", fontSize=10.5, leading=13,
        leftIndent=10, bulletIndent=0,
    )
    return name, contact, section, body, role, bullet


def render(resume: TailoredResume) -> bytes:
    """Render a TailoredResume → PDF bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"{resume.name} — Resume",
        author=resume.name,
        keywords=", ".join(resume.keywords_added or resume.skills or []),
    )

    s_name, s_contact, s_section, s_body, s_role, s_bullet = _styles()
    story = []

    # ── Header ──────────────────────────────────────────────────────────────
    story.append(Paragraph(_escape(resume.name or " "), s_name))
    contact_bits = [resume.email, resume.phone, resume.location]
    contact_line = "  ·  ".join(_escape(c) for c in contact_bits if c)
    if contact_line:
        story.append(Paragraph(contact_line, s_contact))

    # ── Summary ─────────────────────────────────────────────────────────────
    if (resume.summary or "").strip():
        story.append(Paragraph("Summary", s_section))
        story.append(Paragraph(_escape(resume.summary), s_body))

    # ── Skills ──────────────────────────────────────────────────────────────
    if resume.skills:
        story.append(Paragraph("Skills", s_section))
        story.append(Paragraph(_escape(" · ".join(resume.skills)), s_body))

    # ── Experience ──────────────────────────────────────────────────────────
    if resume.experience:
        story.append(Paragraph("Experience", s_section))
        for exp in resume.experience:
            header = f"{_escape(exp.role)} — {_escape(exp.company)}"
            story.append(Paragraph(header, s_role))
            if exp.bullets:
                items = [
                    ListItem(Paragraph(_escape(b.text), s_bullet),
                             leftIndent=6, value="•")
                    for b in exp.bullets
                ]
                story.append(ListFlowable(items, bulletType="bullet",
                                          start="•", leftIndent=12))

    # ── Education ───────────────────────────────────────────────────────────
    if resume.education:
        story.append(Paragraph("Education", s_section))
        for line in resume.education:
            story.append(Paragraph(_escape(line), s_body))

    # ReportLab requires *something* to render, even for an empty resume.
    if not story:
        story.append(Paragraph(" ", s_body))

    doc.build(story)
    return buf.getvalue()


def render_to_path(resume: TailoredResume, path: str) -> str:
    """Render and write the PDF to `path`. Creates parent dirs. Returns `path`."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(render(resume))
    return path


def _escape(s: Optional[str]) -> str:
    """ReportLab's mini-HTML interprets <>& — escape so user text is literal."""
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))
