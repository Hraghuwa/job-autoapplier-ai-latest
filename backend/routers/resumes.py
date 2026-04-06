"""Resume CRUD API routes — SQLite compatible (string UUIDs)."""
import uuid
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.resume import (
    Resume, ResumeStatus, ResumeSection, ResumeSectionType
)

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class SectionData(BaseModel):
    type: str
    title: str
    order: int = 0
    data: dict = {}
    is_visible: bool = True

class SectionOut(BaseModel):
    id: str
    type: str
    title: str
    order: int
    data: dict
    is_visible: bool

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_instance(cls, obj):
        return cls(
            id=str(obj.id),
            type=obj.type.value if hasattr(obj.type, 'value') else str(obj.type),
            title=obj.title,
            order=obj.order,
            data=obj.data or {},
            is_visible=obj.is_visible,
        )


class ResumeCreate(BaseModel):
    title: str = "Untitled Resume"
    template_id: Optional[str] = None


class ResumeUpdate(BaseModel):
    title: Optional[str] = None
    template_id: Optional[str] = None
    color_scheme: Optional[str] = None
    font_pairing: Optional[str] = None
    status: Optional[str] = None
    content: Optional[dict] = None


class ResumeOut(BaseModel):
    id: str
    title: str
    template_id: Optional[str]
    color_scheme: str
    font_pairing: str
    status: str
    ats_score: Optional[int]
    thumbnail_url: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_instance(cls, obj):
        return cls(
            id=str(obj.id),
            title=obj.title,
            template_id=str(obj.template_id) if obj.template_id else None,
            color_scheme=obj.color_scheme or "#E94560",
            font_pairing=obj.font_pairing or "default",
            status=obj.status.value if hasattr(obj.status, 'value') else str(obj.status),
            ats_score=obj.ats_score,
            thumbnail_url=obj.thumbnail_url,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class ResumeDetailOut(ResumeOut):
    content: dict
    sections: List[SectionOut]

    @classmethod
    def from_orm_instance(cls, obj):
        return cls(
            id=str(obj.id),
            title=obj.title,
            template_id=str(obj.template_id) if obj.template_id else None,
            color_scheme=obj.color_scheme or "#E94560",
            font_pairing=obj.font_pairing or "default",
            status=obj.status.value if hasattr(obj.status, 'value') else str(obj.status),
            ats_score=obj.ats_score,
            thumbnail_url=obj.thumbnail_url,
            content=obj.content or {},
            sections=[SectionOut.from_orm_instance(s) for s in (obj.sections or [])],
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class SectionUpdate(BaseModel):
    title: Optional[str] = None
    data: Optional[dict] = None
    is_visible: Optional[bool] = None


class ReorderItem(BaseModel):
    id: str
    order: int


class ReorderRequest(BaseModel):
    sections: List[ReorderItem]


# ── Default sections for new resumes ─────────────────────────────

DEFAULT_SECTIONS = [
    {"type": "personal_info", "title": "Personal Information", "order": 0, "data": {
        "full_name": "", "email": "", "phone": "", "location": "",
        "linkedin_url": "", "portfolio_url": "", "avatar_url": ""
    }},
    {"type": "summary", "title": "Professional Summary", "order": 1, "data": {"text": ""}},
    {"type": "experience", "title": "Work Experience", "order": 2, "data": {"items": []}},
    {"type": "education", "title": "Education", "order": 3, "data": {"items": []}},
    {"type": "skills", "title": "Skills", "order": 4, "data": {"categories": []}},
    {"type": "projects", "title": "Projects", "order": 5, "data": {"items": []}},
    {"type": "certifications", "title": "Certifications", "order": 6, "data": {"items": []}},
]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ResumeOut])
async def list_resumes(
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all resumes for the current user."""
    q = select(Resume).where(Resume.user_id == str(user.id))

    if search:
        q = q.where(Resume.title.ilike(f"%{search}%"))
    if status_filter:
        q = q.where(Resume.status == status_filter)

    q = q.order_by(desc(Resume.updated_at)).offset(offset).limit(limit)
    result = await db.execute(q)
    resumes = result.scalars().all()
    return [ResumeOut.from_orm_instance(r) for r in resumes]


@router.post("", response_model=ResumeDetailOut, status_code=201)
async def create_resume(
    body: ResumeCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new resume with default sections."""
    resume_id = str(uuid.uuid4())
    resume = Resume(
        id=resume_id,
        user_id=str(user.id),
        title=body.title,
        template_id=body.template_id or None,
        content={},
        status=ResumeStatus.draft,
    )
    db.add(resume)

    # Create default sections
    for sec in DEFAULT_SECTIONS:
        section = ResumeSection(
            id=str(uuid.uuid4()),
            resume_id=resume_id,
            type=ResumeSectionType(sec["type"]),
            title=sec["title"],
            order=sec["order"],
            data=sec["data"],
        )
        db.add(section)

    await db.flush()

    # Reload with sections
    result = await db.execute(
        select(Resume)
        .where(Resume.id == resume_id)
        .options(selectinload(Resume.sections))
    )
    fresh = result.scalar_one()
    return ResumeDetailOut.from_orm_instance(fresh)


@router.get("/{resume_id}", response_model=ResumeDetailOut)
async def get_resume(
    resume_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single resume with all sections."""
    result = await db.execute(
        select(Resume)
        .where(Resume.id == resume_id, Resume.user_id == str(user.id))
        .options(selectinload(Resume.sections))
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(404, "Resume not found")
    return ResumeDetailOut.from_orm_instance(resume)


@router.put("/{resume_id}", response_model=ResumeOut)
async def update_resume(
    resume_id: str,
    body: ResumeUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update resume metadata."""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == str(user.id))
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(404, "Resume not found")

    if body.title is not None:
        resume.title = body.title
    if body.template_id is not None:
        resume.template_id = body.template_id or None
    if body.color_scheme is not None:
        resume.color_scheme = body.color_scheme
    if body.font_pairing is not None:
        resume.font_pairing = body.font_pairing
    if body.status is not None:
        resume.status = ResumeStatus(body.status)
    if body.content is not None:
        resume.content = body.content

    resume.updated_at = datetime.utcnow()
    await db.flush()
    return ResumeOut.from_orm_instance(resume)


@router.delete("/{resume_id}", status_code=204)
async def delete_resume(
    resume_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a resume and all its sections."""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == str(user.id))
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(404, "Resume not found")
    await db.delete(resume)


@router.post("/{resume_id}/duplicate", response_model=ResumeDetailOut, status_code=201)
async def duplicate_resume(
    resume_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Duplicate a resume with all its sections."""
    result = await db.execute(
        select(Resume)
        .where(Resume.id == resume_id, Resume.user_id == str(user.id))
        .options(selectinload(Resume.sections))
    )
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(404, "Resume not found")

    new_id = str(uuid.uuid4())
    clone = Resume(
        id=new_id,
        user_id=str(user.id),
        title=f"{original.title} (Copy)",
        template_id=original.template_id,
        content=original.content,
        color_scheme=original.color_scheme,
        font_pairing=original.font_pairing,
        status=ResumeStatus.draft,
    )
    db.add(clone)

    for sec in original.sections:
        new_sec = ResumeSection(
            id=str(uuid.uuid4()),
            resume_id=new_id,
            type=sec.type,
            title=sec.title,
            order=sec.order,
            data=sec.data.copy() if sec.data else {},
            is_visible=sec.is_visible,
        )
        db.add(new_sec)

    await db.flush()

    result = await db.execute(
        select(Resume)
        .where(Resume.id == new_id)
        .options(selectinload(Resume.sections))
    )
    fresh = result.scalar_one()
    return ResumeDetailOut.from_orm_instance(fresh)


# ── Section Routes ────────────────────────────────────────────────────────────

@router.post("/{resume_id}/sections", response_model=SectionOut, status_code=201)
async def add_section(
    resume_id: str,
    body: SectionData,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new section to a resume."""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == str(user.id))
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(404, "Resume not found")

    section = ResumeSection(
        id=str(uuid.uuid4()),
        resume_id=resume_id,
        type=ResumeSectionType(body.type),
        title=body.title,
        order=body.order,
        data=body.data,
        is_visible=body.is_visible,
    )
    db.add(section)
    await db.flush()
    return SectionOut.from_orm_instance(section)


@router.put("/{resume_id}/sections/{section_id}", response_model=SectionOut)
async def update_section(
    resume_id: str,
    section_id: str,
    body: SectionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a section's data."""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == str(user.id))
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Resume not found")

    result = await db.execute(
        select(ResumeSection).where(
            ResumeSection.id == section_id,
            ResumeSection.resume_id == resume_id
        )
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(404, "Section not found")

    if body.title is not None:
        section.title = body.title
    if body.data is not None:
        section.data = body.data
    if body.is_visible is not None:
        section.is_visible = body.is_visible

    section.updated_at = datetime.utcnow()
    await db.flush()
    return SectionOut.from_orm_instance(section)


@router.delete("/{resume_id}/sections/{section_id}", status_code=204)
async def delete_section(
    resume_id: str,
    section_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a section from a resume."""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == str(user.id))
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Resume not found")

    result = await db.execute(
        select(ResumeSection).where(
            ResumeSection.id == section_id,
            ResumeSection.resume_id == resume_id
        )
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(404, "Section not found")

    await db.delete(section)


@router.put("/{resume_id}/sections/reorder")
async def reorder_sections(
    resume_id: str,
    body: ReorderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reorder sections within a resume."""
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == str(user.id))
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Resume not found")

    for item in body.sections:
        result = await db.execute(
            select(ResumeSection).where(
                ResumeSection.id == item.id,
                ResumeSection.resume_id == resume_id
            )
        )
        section = result.scalar_one_or_none()
        if section:
            section.order = item.order

    return {"message": "Sections reordered"}
