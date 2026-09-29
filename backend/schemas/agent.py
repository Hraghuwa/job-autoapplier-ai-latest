from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class RunRequest(BaseModel):
    phases: List[int]  # [1], [2], [1,2,3,4], etc.
    dry_run: Optional[bool] = False


class RunResponse(BaseModel):
    run_ids: List[str]
    message: str


class RunStatusResponse(BaseModel):
    id: str           # frontend reads run.id / r.id
    phase: int
    platform: Optional[str]
    status: str
    applied_count: int
    skipped_count: int
    error_count: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):
        if hasattr(obj, "__dict__"):
            return cls(
                id=str(obj.id),
                phase=obj.phase,
                platform=obj.platform,
                status=obj.status.value if hasattr(obj.status, "value") else str(obj.status),
                applied_count=obj.applied_count or 0,
                skipped_count=obj.skipped_count or 0,
                error_count=obj.error_count or 0,
                started_at=obj.started_at,
                completed_at=obj.completed_at,
            )
        return super().model_validate(obj, **kwargs)


class ScheduleRequest(BaseModel):
    cron: str          # e.g. "0 9 * * *"
    phases: List[int]
    enabled: bool = True

class LogResponse(BaseModel):
    id: str
    event_type: str
    message: str
    created_at: datetime
    
    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):
        if hasattr(obj, "__dict__"):
            return cls(
                id=str(obj.id),
                event_type=obj.event_type,
                message=obj.message,
                created_at=obj.created_at,
            )
        return super().model_validate(obj, **kwargs)

