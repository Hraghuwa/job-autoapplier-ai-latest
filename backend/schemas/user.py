from typing import Optional, Any, Dict
from pydantic import BaseModel, EmailStr


class ProfileOut(BaseModel):
    id: str
    user_id: str
    resume_url: Optional[str]
    resume_filename: Optional[str]
    extracted_data: Optional[Dict[str, Any]]
    job_preferences: Optional[Dict[str, Any]]
    autofill_bank: Optional[Dict[str, Any]]
    cover_letter: Optional[str]

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):
        if hasattr(obj, "__dict__"):
            return cls(
                id=str(obj.id),
                user_id=str(obj.user_id),
                resume_url=obj.resume_url,
                resume_filename=obj.resume_filename,
                extracted_data=obj.extracted_data,
                job_preferences=obj.job_preferences,
                autofill_bank=obj.autofill_bank,
                cover_letter=obj.cover_letter,
            )
        return super().model_validate(obj, **kwargs)


class ProfileUpdate(BaseModel):
    autofill_bank: Optional[Dict[str, Any]] = None
    cover_letter: Optional[str] = None
    job_preferences: Optional[Dict[str, Any]] = None


class GeminiKeyRequest(BaseModel):
    api_key: str


class UsageOut(BaseModel):
    tokens_used_today: int
    plan: str
    applies_today: int
    applies_limit: int
