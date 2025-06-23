from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
import uuid
from datetime import datetime
import re

from app.db.base import get_db
from app.models.session import Session
from app.models.chat import Chat
from app.schemas.session import SessionCreate, Session as SessionSchema, SessionUpdate
from app.api.v1.auth import get_current_user
from app.models.user import User
import logging

router = APIRouter(prefix="/session", tags=["session"])
logger = logging.getLogger(__name__)

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
    """
    Get all sessions for the current user with limited chat preview for performance.
    Returns only the first 3 chats per session for session list display.
    """
    # Get sessions without automatic chat loading
    sessions = db.query(Session).filter(
        Session.user_id == current_user.id
    ).order_by(Session.updated_at.desc()).all()
    
    # For each session, load only a preview of chats
    for session in sessions:
        preview_chats = db.query(Chat).filter(
            Chat.session_id == session.id
        ).order_by(Chat.created_at.desc()).limit(3).all()
        session.chats = preview_chats
    
    logger.info(f"Loaded {len(sessions)} sessions with chat previews for user {current_user.id}")
    return sessions

@router.get("/{session_id}", response_model=SessionSchema)
async def get_session(
    *,
    db: Session = Depends(get_db),
    session_id: str,
    current_user: User = Depends(get_current_user),
    request: Request,
    load_full_chats: Optional[bool] = Query(None, description="Load all chats or just preview (first 5)")
) -> Any:
    """
    Get a specific session by ID. Only accessible by the session owner.
    
    Automatically determines whether to load full chats based on:
    1. load_full_chats query parameter (if provided)
    2. HTTP Referer header (if visiting session-specific page)
    3. Defaults to preview mode (first 5 chats) for performance
    """
    # Get session without chats first (avoid automatic loading)
    session = db.query(Session).filter(
        Session.id == session_id,
        Session.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Smart detection of whether to load full chats
    should_load_full_chats = False
    
    if load_full_chats is not None:
        # Explicit query parameter takes precedence
        should_load_full_chats = load_full_chats
        logger.info(f"Using explicit load_full_chats={load_full_chats} for session {session_id}")
    else:
        # Auto-detect based on HTTP Referer header
        referer = request.headers.get("referer", "")
        
        # Check if the referer URL contains the session ID (indicating user is on session page)
        if referer and session_id in referer:
            # Additional check: ensure it's a session-specific page (not just a list containing the ID)
            if re.search(f'/searchdetails/{re.escape(session_id)}', referer):
                should_load_full_chats = True
                logger.info(f"Auto-detected session visit from referer for session {session_id}")
            elif 'searchdetails' in referer:
                should_load_full_chats = True
                logger.info(f"Auto-detected searchdetails page visit for session {session_id}")
    
    # Load chats based on determination
    if should_load_full_chats:
        # Load all chats when session is specifically visited
        chats = db.query(Chat).filter(
            Chat.session_id == session_id
        ).order_by(Chat.created_at.desc()).all()
        logger.info(f"Loaded full chat history for session {session_id}: {len(chats)} chats")
    else:
        # Load only first 5 chats for session preview/list
        chats = db.query(Chat).filter(
            Chat.session_id == session_id
        ).order_by(Chat.created_at.desc()).limit(5).all()
        logger.info(f"Loaded preview chats for session {session_id}: {len(chats)} chats (preview mode)")
    
    # Manually assign chats to avoid SQLAlchemy relationship loading
    session.chats = chats
    
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
    Get all sessions created by the current user, ordered by most recent first.
    Returns only the first 3 chats per session for performance.
    """
    # Get sessions without automatic chat loading
    sessions = db.query(Session).filter(
        Session.user_id == current_user.id
    ).order_by(Session.updated_at.desc()).all()
    
    # For each session, load only a preview of chats
    for session in sessions:
        preview_chats = db.query(Chat).filter(
            Chat.session_id == session.id
        ).order_by(Chat.created_at.desc()).limit(3).all()
        session.chats = preview_chats
    
    logger.info(f"Loaded {len(sessions)} user sessions with chat previews for user {current_user.id}")
    return sessions 