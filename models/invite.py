from sqlalchemy import Boolean, Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base
from datetime import datetime, timedelta
import uuid
import secrets
import string

class Invite(Base):
    __tablename__ = "invites"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    generated_by = Column(String, ForeignKey("users.id"), nullable=False)
    invite_code = Column(String(12), unique=True, nullable=False, index=True)
    max_uses = Column(Integer, default=1, nullable=False)
    current_uses = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)  # NULL means no expiration
    used_at = Column(DateTime, nullable=True)  # When the invite was first used
    used_by = Column(String, nullable=True)  # User ID who used the invite
    
    # Relationships
    generator = relationship("User", back_populates="generated_invites")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.invite_code:
            self.invite_code = self.generate_invite_code()
    
    @staticmethod
    def generate_invite_code(length=12):
        """Generate a random invite code"""
        characters = string.ascii_letters + string.digits
        return ''.join(secrets.choice(characters) for _ in range(length))
    
    def is_valid(self):
        """Check if the invite is still valid"""
        if not self.is_active:
            return False
        
        if self.current_uses >= self.max_uses:
            return False
        
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        
        return True
    
    def use_invite(self, user_id=None):
        """Use the invite (increment usage count)"""
        if not self.is_valid():
            return False
        
        self.current_uses += 1
        
        # Mark as used if this is the first use
        if self.current_uses == 1:
            self.used_at = datetime.utcnow()
            if user_id:
                self.used_by = user_id
        
        # Deactivate if max uses reached
        if self.current_uses >= self.max_uses:
            self.is_active = False
        
        return True
    
    def can_be_used(self):
        """Check if invite can be used (has remaining uses)"""
        return self.is_valid() and self.current_uses < self.max_uses
    
    def remaining_uses(self):
        """Get remaining uses for this invite"""
        if not self.is_valid():
            return 0
        return max(0, self.max_uses - self.current_uses) 