from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid
from datetime import datetime

from app.core.security import get_password_hash, get_current_user, verify_password, create_verification_token_with_expiry, verify_verification_token
from app.core.email import send_verification_email
from app.core.email_simple import send_verification_email_simple
from app.db.base import get_db
from app.models.user import User
from app.schemas.user import UserCreate, User as UserSchema, UserBase, UserLogin, EmailVerification, ResendVerificationEmail

router = APIRouter(prefix="/user", tags=["user"])

@router.post("/register", response_model=UserSchema)
def register(*, db: Session = Depends(get_db), user_in: UserCreate) -> Any:
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="A user with this email already exists.",
        )
    
        # Generate email verification token
    verification_token, expires_at = create_verification_token_with_expiry()
    
    
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
        is_active=True,
        isEmailVerified=False,
        email_verification_token=verification_token,
        email_verification_token_expires=expires_at
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # Send verification email
    try:
        verification_link = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
        success = send_verification_email_simple(
            email_to=user_in.email,
            verification_link=verification_link,
            user_name=user_in.first_name or ""
        )
        if not success:
            print("Failed to send verification email using simple method")
    except Exception as e:
        # Log the error but don't fail registration
        print(f"Failed to send verification email: {e}")
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

@router.post("/verify-email")
def verify_email(
    *,
    db: Session = Depends(get_db),
    verification_data: EmailVerification
) -> Any:
    """
    Verify user's email address using the verification token
    """
    user = db.query(User).filter(
        User.email_verification_token == verification_data.token
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=400,
            detail="Invalid verification token"
        )
    
    if not verify_verification_token(
        verification_data.token, 
        user.email_verification_token, 
        user.email_verification_token_expires
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification token"
        )
    
    # Mark email as verified and clear verification token
    user.isEmailVerified = True
    user.email_verification_token = None
    user.email_verification_token_expires = None
    
    db.add(user)
    db.commit()
    
    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
def resend_verification_email(
    *,
    db: Session = Depends(get_db),
    email_data: ResendVerificationEmail
) -> Any:
    """
    Resend verification email to user
    """
    user = db.query(User).filter(User.email == email_data.email).first()
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
    
    if user.isEmailVerified:
        raise HTTPException(
            status_code=400,
            detail="Email is already verified"
        )
    
    # Generate new verification token
    verification_token, expires_at = create_verification_token_with_expiry()
    
    user.email_verification_token = verification_token
    user.email_verification_token_expires = expires_at
    
    db.add(user)
    db.commit()
    
    # Send verification email
    try:
        verification_link = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
        send_verification_email(
            email_to=email_data.email,
            verification_link=verification_link,
            user_name=user.first_name or ""
        )
        return {"message": "Verification email sent successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to send verification email"
        ) 

