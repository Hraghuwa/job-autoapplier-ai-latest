from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(..., max_length=255)
    email: EmailStr
    # bcrypt only reads the first 72 bytes; cap well inside that.
    password: str = Field(..., min_length=8, max_length=72)
    referral_code: Optional[str] = Field(None, max_length=32)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    plan: str
    is_admin: bool

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):
        if hasattr(obj, "__dict__"):
            data = {
                "id": str(obj.id),
                "email": obj.email,
                "name": obj.name,
                "plan": obj.plan.value if hasattr(obj.plan, "value") else str(obj.plan),
                "is_admin": obj.is_admin,
            }
            return cls(**data)
        return super().model_validate(obj, **kwargs)
