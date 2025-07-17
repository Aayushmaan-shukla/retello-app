from sqlalchemy import Boolean, Column, String, DateTime
from sqlalchemy.orm import relationship
from app.db.base import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)  # Made nullable for OTP auth
    password = Column(String, nullable=True)  # Made nullable for OTP auth
    phone = Column(String, unique=True, index=True, nullable=False)  # Made required and unique
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    pincode = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    forgot_password_id = Column(String, nullable=True)
    # Add field to track if user signed up via OTP
    auth_method = Column(String, default="otp")  # "otp" or "email"

    # Relationships
    sessions = relationship("Session", back_populates="user")
    chats = relationship("Chat", back_populates="user") 