from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime

class ChatBase(BaseModel):
    prompt: Optional[str] = None
    user_input: Optional[str] = None

class ChatCreate(ChatBase):
    @property
    def input_text(self) -> str:
        return self.user_input or self.prompt or ""

    def __init__(self, **data):
        super().__init__(**data)
        # If prompt is provided but user_input isn't, copy prompt to user_input
        if self.prompt and not self.user_input:
            self.user_input = self.prompt
        # If user_input is provided but prompt isn't, copy user_input to prompt
        elif self.user_input and not self.prompt:
            self.prompt = self.user_input

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