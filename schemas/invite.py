from typing import Optional
from pydantic import BaseModel, Field, validator
from datetime import datetime

class InviteBase(BaseModel):
    max_uses: int = Field(default=1, ge=1, le=10, description="Maximum number of uses for this invite")
    expires_at: Optional[datetime] = Field(default=None, description="Expiration date for the invite")

class InviteCreate(InviteBase):
    pass

class InviteResponse(InviteBase):
    id: str
    generated_by: str
    invite_code: str
    current_uses: int
    is_active: bool
    created_at: datetime
    used_at: Optional[datetime] = None
    used_by: Optional[str] = None
    
    class Config:
        from_attributes = True

class InviteListResponse(BaseModel):
    id: str
    invite_code: str
    max_uses: int
    current_uses: int
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime] = None
    used_at: Optional[datetime] = None
    remaining_uses: int
    
    class Config:
        from_attributes = True

class InviteValidateResponse(BaseModel):
    valid: bool
    message: str
    invite_code: Optional[str] = None
    remaining_uses: Optional[int] = None
    expires_at: Optional[datetime] = None

class InviteUseRequest(BaseModel):
    phone: Optional[str] = Field(default=None, description="Phone number of the user using the invite")
    
class InviteUseResponse(BaseModel):
    success: bool
    message: str
    access_token: Optional[str] = None
    token_type: Optional[str] = "bearer"
    user_id: Optional[str] = None
    invite_code: str
    is_guest_user: bool = True  # Flag to indicate this is a guest user via invite

class InviteGenerateResponse(BaseModel):
    invite_code: str
    invite_link: str
    max_uses: int
    expires_at: Optional[datetime] = None
    created_at: datetime
    
class InviteStatsResponse(BaseModel):
    total_invites_generated: int
    active_invites: int
    used_invites: int
    remaining_invite_limit: int
    max_invite_limit: int
    
# Request model for generating invite with optional parameters
class InviteGenerateRequest(BaseModel):
    max_uses: Optional[int] = Field(default=1, ge=1, le=10, description="Maximum uses per invite")
    expires_in_hours: Optional[int] = Field(default=None, ge=1, le=8760, description="Expiration time in hours")
    
    @validator('expires_in_hours')
    def validate_expires_in_hours(cls, v):
        if v is not None and v <= 0:
            raise ValueError('expires_in_hours must be greater than 0')
        return v 