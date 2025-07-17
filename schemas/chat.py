from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, field_validator
from datetime import datetime

class ChatBase(BaseModel):
    prompt: Optional[str] = None

class ChatCreate(ChatBase):
    @property
    def input_text(self) -> str:
        return self.prompt or ""

class Chat(ChatBase):
    id: str
    user_id: str
    session_id: str
    response: Optional[str] = None
    phones: List[Dict[str, Any]] = []
    current_params: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    button_text: Optional[str] = None
    why_this_phone: List[str] = []
    has_more: bool = False

    @field_validator('why_this_phone', mode='before')
    @classmethod
    def validate_why_this_phone(cls, v):
        """Convert string to list if needed, handle None values"""
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, list):
            return [str(item) for item in v if item is not None]
        return []

    @field_validator('phones', mode='before')
    @classmethod
    def validate_phones(cls, v):
        """Ensure phones is always a list"""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return []

    @field_validator('current_params', mode='before')
    @classmethod
    def validate_current_params(cls, v):
        """Ensure current_params is a dict"""
        if v is None:
            return {}
        if isinstance(v, dict):
            return v
        return {}

    class Config:
        from_attributes = True 