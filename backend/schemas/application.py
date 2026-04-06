from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel


class ApplicationOut(BaseModel):
    id: str
    platform: str
    job_title: str
    company: str
    location: Optional[str]
    job_url: Optional[str]
    match_score: Optional[int]
    matched_skills: Optional[List[Any]]
    missing_skills: Optional[List[Any]]
    status: str
    applied_at: datetime
    cover_letter_used: Optional[str]

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):
        if hasattr(obj, "__dict__"):
            return cls(
                id=str(obj.id),
                platform=obj.platform,
                job_title=obj.job_title,
                company=obj.company,
                location=obj.location,
                job_url=obj.job_url,
                match_score=obj.match_score,
                matched_skills=obj.matched_skills,
                missing_skills=obj.missing_skills,
                status=obj.status.value if hasattr(obj.status, "value") else str(obj.status),
                applied_at=obj.applied_at,
                cover_letter_used=obj.cover_letter_used,
            )
        return super().model_validate(obj, **kwargs)


class ApplicationDetail(ApplicationOut):
    jd_text: Optional[str]
    match_reason: Optional[str]
    interview_prep: Optional[dict]

    @classmethod
    def model_validate(cls, obj, **kwargs):
        if hasattr(obj, "__dict__"):
            base = ApplicationOut.model_validate(obj)
            return cls(
                **base.model_dump(),
                jd_text=obj.jd_text,
                match_reason=obj.match_reason,
                interview_prep=obj.interview_prep,
            )
        return super().model_validate(obj, **kwargs)


class StatusUpdate(BaseModel):
    status: str  # applied / viewed / shortlisted / interview / offer / rejected


class AnalyticsOut(BaseModel):
    total: int
    total_applied: int          # alias for dashboard
    this_week: int
    this_month: int
    by_platform: dict
    by_status: dict
    response_rate: float
    top_companies: List[str]
    avg_match_score: Optional[float] = None
    daily_applies: Optional[List[dict]] = None
