from typing import Optional, List, Dict, Any
from pydantic import BaseModel
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

    class Config:
        from_attributes = True 