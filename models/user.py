from sqlalchemy import Boolean, Column, String, DateTime
from sqlalchemy.orm import relationship
from app.db.base import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    phone = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    pincode = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    forgot_password_id = Column(String, nullable=True)
    isEmailVerified = Column(Boolean, default=False)
    email_verification_token = Column(String, nullable=True)
    email_verification_token_expires = Column(DateTime, nullable=True)

    # Relationships
    sessions = relationship("Session", back_populates="user")
    chats = relationship("Chat", back_populates="user") 