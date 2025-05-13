from sqlalchemy import Boolean, Column, String, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from app.db.base import Base

class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))
    is_public = Column(Boolean, default=False)
    name = Column(String, default="Untitled Session")
    
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, default=func.now())

    # Relationships
    user = relationship("User", back_populates="sessions")
    chats = relationship("Chat", back_populates="session") 