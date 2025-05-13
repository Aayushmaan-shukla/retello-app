from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid
from datetime import datetime

from app.core.security import get_password_hash, get_current_user, verify_password
from app.db.base import get_db
from app.models.user import User
from app.schemas.user import UserCreate, User as UserSchema, UserBase, UserLogin

router = APIRouter(prefix="/user", tags=["user"])

@router.post("/register", response_model=UserSchema)
def register(*, db: Session = Depends(get_db), user_in: UserCreate) -> Any:
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="A user with this email already exists.",
        )
    
    db_user = User(
        id=str(uuid.uuid4()),
        email=user_in.email,
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        phone=user_in.phone,
        gender=user_in.gender,
        pincode=user_in.pincode,
        password=get_password_hash(user_in.password),
        created_at=datetime.utcnow(),
        is_active=True
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.put("/profile", response_model=UserSchema)
def update_profile(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    user_update: UserBase
) -> Any:
    """
    Update user profile information.
    """
    # Update user fields
    for field, value in user_update.dict(exclude_unset=True).items():
        if hasattr(current_user, field):
            setattr(current_user, field, value)
    
    current_user.updated_at = datetime.utcnow()
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user

@router.get("/info", response_model=UserSchema)
def get_user_info(
    *,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get current user information using JWT token authentication
    """
    return current_user 