"""
Import all models so SQLAlchemy registers them with database.Base metadata.
All model files use backend.database.Base (DeclarativeBase subclass).
"""
from backend.database import Base  # noqa: F401 — ensure Base is available

from backend.models.user import User, PlanEnum  # noqa: F401
from backend.models.profile import UserProfile  # noqa: F401
from backend.models.application import Application, ApplicationStatus, JobOutcome  # noqa: F401
from backend.models.agent_run import AgentRun, AgentLog, RunStatus  # noqa: F401
from backend.models.quota import UsageQuota  # noqa: F401
from backend.models.payment import Payment, PaymentStatus  # noqa: F401
from backend.models.notification import Notification  # noqa: F401
from backend.models.referral import Referral, ReferralStatus  # noqa: F401
from backend.models.graph import GraphNodePosition  # noqa: F401

# Resume Builder models
from backend.models.resume import (  # noqa: F401
    Resume, ResumeStatus, ResumeSection, ResumeSectionType,
    ResumeTemplate, CoverLetter,
    AIRequest, AIFeedback, AIPromptTemplate,
    SiteSettings, FeatureFlag,
)

# Aliases for backward compat
PlanType = PlanEnum
