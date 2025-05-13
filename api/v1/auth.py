from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from app.core.config import settings
from app.core.security import create_access_token, verify_password, get_password_hash
from app.db.base import get_db
from app.models.user import User
from app.schemas.user import UserLogin, Token, TokenPayload

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

async def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False}  # Disable expiration verification
        )
        token_data = TokenPayload(**payload)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = db.query(User).filter(User.id == token_data.sub).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.post("/login", response_model=Token)
def login(
    *,
    db: Session = Depends(get_db),
    user_data: UserLogin
) -> Any:
    user = db.query(User).filter(User.email == user_data.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Email not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="User is not active")
    if not verify_password(user_data.password, user.password):
        raise HTTPException(status_code=400, detail="Incorrect password")
    
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
    }

@router.post("/reset-password")
async def reset_password(
    current_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Any:
    if not verify_password(current_password, current_user.password):
        raise HTTPException(status_code=400, detail="Incorrect password")
    
    current_user.password = get_password_hash(new_password)
    db.commit()
    return {"message": "Password updated successfully"}

@router.post("/forgot-password")
async def forgot_password(email: str, db: Session = Depends(get_db)) -> Any:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # In a real application, you would:
    # 1. Generate a unique token
    # 2. Save it to the user's forgot_password_id
    # 3. Send an email with a reset link
    # For now, we'll just update the forgot_password_id
    user.forgot_password_id = "temporary_token"  # In real app, use a secure token
    db.commit()
    return {"message": "Password reset instructions sent"}

@router.post("/new-password")
async def new_password(
    forgot_password_id: str,
    new_password: str,
    db: Session = Depends(get_db)
) -> Any:
    user = db.query(User).filter(User.forgot_password_id == forgot_password_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Invalid reset token")
    
    user.password = get_password_hash(new_password)
    user.forgot_password_id = None
    db.commit()
    return {"message": "Password updated successfully"} 