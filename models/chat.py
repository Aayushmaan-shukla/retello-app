from sqlalchemy import Column, String, ForeignKey, DateTime, func, JSON, Boolean
from sqlalchemy.orm import relationship
from app.db.base import Base

class Chat(Base):
    __tablename__ = "chats"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"))
    prompt = Column(String)
    response = Column(String, nullable=True)
    phones = Column(JSON, default=list)
    current_params = Column(JSON)
    button_text = Column(String, nullable=True)
    why_this_phone = Column(JSON, default=list)
    has_more = Column(Boolean, default=False, nullable=False)  # New field for has_more flag
    
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, default=func.now())

    # Relationships
    user = relationship("User", back_populates="chats")
    session = relationship("Session", back_populates="chats") 