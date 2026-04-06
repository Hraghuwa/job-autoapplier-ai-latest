"""Resume Builder domain models — SQLite compatible."""
import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, Text, ForeignKey, DateTime, Enum, Float, JSON
from sqlalchemy.orm import relationship
from backend.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class ResumeStatus(str, enum.Enum):
    draft = "draft"
    completed = "completed"
    archived = "archived"


class Resume(Base):
    __tablename__ = 'resumes'

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    title = Column(String, nullable=False, default="Untitled Resume")
    template_id = Column(String, ForeignKey('resume_templates.id', ondelete='SET NULL'), nullable=True)
    content = Column(JSON, default=dict)
    color_scheme = Column(String, default="#E94560")
    font_pairing = Column(String, default="default")
    status = Column(Enum(ResumeStatus, native_enum=False, length=50), default=ResumeStatus.draft)
    thumbnail_url = Column(String, nullable=True)
    ats_score = Column(Integer, nullable=True)
    last_exported_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="resumes")
    template = relationship("ResumeTemplate", back_populates="resumes")
    sections = relationship("ResumeSection", back_populates="resume", cascade="all, delete-orphan",
                           order_by="ResumeSection.order")
    cover_letters = relationship("CoverLetter", back_populates="resume", cascade="all, delete-orphan")


class ResumeSectionType(str, enum.Enum):
    personal_info = "personal_info"
    summary = "summary"
    experience = "experience"
    education = "education"
    skills = "skills"
    projects = "projects"
    certifications = "certifications"
    languages = "languages"
    awards = "awards"
    publications = "publications"
    volunteer = "volunteer"
    custom = "custom"


class ResumeSection(Base):
    __tablename__ = 'resume_sections'

    id = Column(String, primary_key=True, default=gen_uuid)
    resume_id = Column(String, ForeignKey('resumes.id', ondelete='CASCADE'), nullable=False, index=True)
    type = Column(Enum(ResumeSectionType, native_enum=False, length=50), nullable=False)
    title = Column(String, nullable=False)
    order = Column(Integer, nullable=False, default=0)
    data = Column(JSON, default=dict)
    is_visible = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    resume = relationship("Resume", back_populates="sections")


class ResumeTemplate(Base):
    __tablename__ = 'resume_templates'

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    html_template = Column(Text, nullable=False)
    css_styles = Column(Text, nullable=False)
    category = Column(String, default="professional")
    is_premium = Column(Boolean, default=False)
    color_options = Column(JSON, default=list)
    font_options = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    download_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    resumes = relationship("Resume", back_populates="template")


class CoverLetter(Base):
    __tablename__ = 'cover_letters'

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    resume_id = Column(String, ForeignKey('resumes.id', ondelete='SET NULL'), nullable=True)
    title = Column(String, nullable=False, default="Untitled Cover Letter")
    target_company = Column(String, nullable=True)
    target_role = Column(String, nullable=True)
    job_description = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    template_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="cover_letters")
    resume = relationship("Resume", back_populates="cover_letters")


class AIRequest(Base):
    __tablename__ = 'ai_requests'

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    type = Column(String, nullable=False)
    input_data = Column(JSON, nullable=False)
    output_data = Column(JSON, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    cost_estimate = Column(Float, nullable=True)
    prompt_version = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="ai_requests")
    feedback = relationship("AIFeedback", back_populates="request", cascade="all, delete-orphan")


class AIFeedback(Base):
    __tablename__ = 'ai_feedback'

    id = Column(String, primary_key=True, default=gen_uuid)
    request_id = Column(String, ForeignKey('ai_requests.id', ondelete='CASCADE'), nullable=False)
    suggestion_uuid = Column(String, nullable=False, index=True)
    accepted = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    request = relationship("AIRequest", back_populates="feedback")


class AIPromptTemplate(Base):
    __tablename__ = 'ai_prompt_templates'

    id = Column(String, primary_key=True, default=gen_uuid)
    type = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    system_prompt = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    acceptance_rate = Column(Float, nullable=True)
    sample_count = Column(Integer, default=0)
    flagged = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SiteSettings(Base):
    __tablename__ = 'site_settings'

    id = Column(String, primary_key=True, default=gen_uuid)
    key = Column(String, unique=True, nullable=False, index=True)
    value = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FeatureFlag(Base):
    __tablename__ = 'feature_flags'

    id = Column(String, primary_key=True, default=gen_uuid)
    key = Column(String, unique=True, nullable=False, index=True)
    enabled = Column(Boolean, default=True)
    tier = Column(String, nullable=True)
    description = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
