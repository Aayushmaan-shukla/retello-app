from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid
from datetime import datetime

from app.db.base import get_db
from app.models.session import Session
from app.schemas.session import SessionCreate, Session as SessionSchema, SessionUpdate
from app.api.v1.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/session", tags=["session"])

@router.post("", response_model=SessionSchema)
async def create_session(
    *,
    db: Session = Depends(get_db),
    session_in: SessionCreate,
    current_user: User = Depends(get_current_user)
) -> Any:
    db_session = Session(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        name=session_in.name,
        is_public=session_in.is_public
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session

@router.put("/{session_id}", response_model=SessionSchema)
async def update_session(
    *,
    db: Session = Depends(get_db),
    session_id: str,
    session_in: SessionUpdate,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Update a session. Only accessible by the session owner.
    """
    session = db.query(Session).filter(
        Session.id == session_id,
        Session.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    for field, value in session_in.dict(exclude_unset=True).items():
        setattr(session, field, value)
    
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session

@router.get("", response_model=List[SessionSchema])
async def get_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    sessions = db.query(Session).filter(
        (Session.user_id == current_user.id) | (Session.is_public == True)
    ).all()
    return sessions

@router.get("/{session_id}", response_model=SessionSchema)
async def get_session(
    *,
    db: Session = Depends(get_db),
    session_id: str,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get a specific session by ID. Only accessible by the session owner.
    """
    session = db.query(Session).filter(
        Session.id == session_id,
        Session.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

@router.delete("/{session_id}")
async def delete_session(
    *,
    db: Session = Depends(get_db),
    session_id: str,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Delete a session. Only accessible by the session owner.
    """
    session = db.query(Session).filter(
        Session.id == session_id,
        Session.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    db.delete(session)
    db.commit()
    return {"message": "Session deleted successfully"}

@router.get("/user/sessions", response_model=List[SessionSchema])
async def get_user_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get all sessions created by the current user, ordered by most recent first
    """
    sessions = db.query(Session).filter(
        Session.user_id == current_user.id
    ).order_by(Session.updated_at.desc()).all()
    return sessions 