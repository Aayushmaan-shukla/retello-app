from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from .chat import Chat

class SessionBase(BaseModel):
    name: Optional[str] = "Untitled Session"
    is_public: Optional[bool] = False

class SessionCreate(SessionBase):
    pass

class SessionUpdate(SessionBase):
    pass

class Session(SessionBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    chats: List[Chat] = [] #for chat history not going with the session 

    class Config:
        from_attributes = True 