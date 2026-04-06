import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, Text, ForeignKey, DateTime, Enum, Date
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from .base import Base

class PlanType(str, enum.Enum):
    free = "free"
    pro = "pro"
    team = "team"

class ApplicationStatus(str, enum.Enum):
    applied = "applied"
    viewed = "viewed"
    shortlisted = "shortlisted"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"

class RunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    paused = "paused"
    limit_reached = "limit_reached"

class PaymentStatus(str, enum.Enum):
    created = "created"
    paid = "paid"
    failed = "failed"

class ReferralStatus(str, enum.Enum):
    pending = "pending"
    rewarded = "rewarded"

class User(Base):
    __tablename__ = 'users'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String)
    name = Column(String)
    plan = Column(Enum(PlanType, native_enum=False, length=50), default=PlanType.free)
    is_admin = Column(Boolean, default=False)
    gemini_key_encrypted = Column(String, nullable=True)
    tokens_used_today = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="user", cascade="all, delete-orphan")
    runs = relationship("AgentRun", back_populates="user", cascade="all, delete-orphan")
    quotas = relationship("UsageQuota", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

class UserProfile(Base):
    __tablename__ = 'user_profiles'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), unique=True)
    resume_url = Column(String)
    resume_hash = Column(String)
    resume_filename = Column(String)
    extracted_data = Column(JSONB)
    job_preferences = Column(JSONB)
    autofill_bank = Column(JSONB)
    cover_letter = Column(Text)
    platform_passwords = Column(JSONB)
    session_cookies = Column(JSONB)
    chrome_profile_path = Column(String)
    fingerprint = Column(JSONB)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="profile")

class Application(Base):
    __tablename__ = 'applications'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    platform = Column(String)
    job_title = Column(String)
    company = Column(String)
    location = Column(String)
    job_url = Column(String)
    jd_text = Column(Text)
    match_score = Column(Integer)
    match_reason = Column(Text)
    matched_skills = Column(JSONB)
    missing_skills = Column(JSONB)
    status = Column(Enum(ApplicationStatus, native_enum=False, length=50), default=ApplicationStatus.applied)
    cover_letter_used = Column(Text)
    interview_prep = Column(JSONB)
    applied_at = Column(DateTime, default=datetime.utcnow)
    job_hash = Column(String, index=True)
    source_url = Column(String)

    user = relationship("User", back_populates="applications")
    logs = relationship("AgentLog", back_populates="application", cascade="all, delete-orphan")
    outcomes = relationship("JobOutcome", back_populates="application", cascade="all, delete-orphan")

class AgentRun(Base):
    __tablename__ = 'agent_runs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    phase = Column(Integer)
    platform = Column(String)
    celery_task_id = Column(String)
    status = Column(Enum(RunStatus, native_enum=False, length=50), default=RunStatus.queued)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    applied_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    config_snapshot = Column(JSONB)

    user = relationship("User", back_populates="runs")
    logs = relationship("AgentLog", back_populates="run", cascade="all, delete-orphan")

class AgentLog(Base):
    __tablename__ = 'agent_logs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey('agent_runs.id', ondelete='CASCADE'))
    application_id = Column(UUID(as_uuid=True), ForeignKey('applications.id', ondelete='SET NULL'), nullable=True)
    event_type = Column(String)
    message = Column(Text)
    screenshot_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("AgentRun", back_populates="logs")
    application = relationship("Application", back_populates="logs")

class UsageQuota(Base):
    __tablename__ = 'usage_quotas'

    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    platform = Column(String, primary_key=True)
    date = Column(Date, primary_key=True)
    applies_count = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)

    user = relationship("User", back_populates="quotas")

class Payment(Base):
    __tablename__ = 'payments'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    razorpay_order_id = Column(String)
    razorpay_payment_id = Column(String)
    amount = Column(Integer)
    currency = Column(String, default='INR')
    plan = Column(String)
    plan_period = Column(String)
    credits_purchased = Column(Integer, nullable=True)
    status = Column(Enum(PaymentStatus, native_enum=False, length=50), default=PaymentStatus.created)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="payments")

class Notification(Base):
    __tablename__ = 'notifications'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    type = Column(String)
    title = Column(String)
    body = Column(Text)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")

class Referral(Base):
    __tablename__ = 'referrals'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    referrer_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    referred_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    code = Column(String, unique=True, nullable=False)
    status = Column(Enum(ReferralStatus, native_enum=False, length=50), default=ReferralStatus.pending)
    rewarded_at = Column(DateTime, nullable=True)

    referrer = relationship("User", foreign_keys=[referrer_id])
    referred = relationship("User", foreign_keys=[referred_id])

class JobOutcome(Base):
    __tablename__ = 'job_outcomes'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey('applications.id', ondelete='CASCADE'))
    outcome = Column(String)
    outcome_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    jd_keywords = Column(JSONB)
    resume_skills = Column(JSONB)

    application = relationship("Application", back_populates="outcomes")
