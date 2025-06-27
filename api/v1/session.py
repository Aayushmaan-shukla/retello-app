from typing import Any, List, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
import uuid
from datetime import datetime
import re

from app.db.base import get_db
from app.models.session import Session
from app.models.chat import Chat
from app.schemas.session import (
    SessionCreate, Session as SessionSchema, SessionUpdate,
    SessionSearchResponse, SessionSearchResult, SessionSearchSession, SessionSearchChat
)
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
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: Optional[int] = Query(12, ge=1, le=50, description="Number of sessions to return"),
    offset: Optional[int] = Query(0, ge=0, description="Number of sessions to skip"),
    load_chat_previews: Optional[bool] = Query(True, description="Whether to load chat previews")
) -> Any:
    """
    Get sessions for the current user with pagination support.
    
    - limit: Number of sessions to return (default: 12, max: 50)
    - offset: Number of sessions to skip for pagination (default: 0)
    - load_chat_previews: Whether to include chat previews (default: True)
    
    Returns sessions ordered by most recently updated first.
    Response headers include pagination metadata.
    """
    # Get total count for pagination metadata
    total_sessions = db.query(Session).filter(
        Session.user_id == current_user.id
    ).count()
    
    # Get sessions with pagination
    sessions_query = db.query(Session).filter(
        Session.user_id == current_user.id
    ).order_by(Session.updated_at.desc())
    
    # Apply pagination
    sessions = sessions_query.offset(offset).limit(limit).all()
    
    # Load chat previews if requested
    if load_chat_previews:
        for session in sessions:
            preview_chats = db.query(Chat).filter(
                Chat.session_id == session.id
            ).order_by(Chat.created_at.desc()).limit(3).all()
            session.chats = preview_chats
    else:
        # Set empty chats list if not loading previews
        for session in sessions:
            session.chats = []
    
    # Add pagination headers
    response.headers["X-Total-Count"] = str(total_sessions)
    response.headers["X-Page-Size"] = str(limit)
    response.headers["X-Page-Offset"] = str(offset)
    response.headers["X-Has-More"] = str(offset + limit < total_sessions)
    
    logger.info(f"Loaded {len(sessions)} sessions (offset: {offset}, limit: {limit}, total: {total_sessions}) with chat previews for user {current_user.id}")
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
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: Optional[int] = Query(12, ge=1, le=50, description="Number of sessions to return"),
    offset: Optional[int] = Query(0, ge=0, description="Number of sessions to skip"),
    load_chat_previews: Optional[bool] = Query(True, description="Whether to load chat previews")
) -> Any:
    """
    Get sessions created by the current user with pagination support.
    
    - limit: Number of sessions to return (default: 12, max: 50)  
    - offset: Number of sessions to skip for pagination (default: 0)
    - load_chat_previews: Whether to include chat previews (default: True)
    
    Returns sessions ordered by most recently updated first.
    Response headers include pagination metadata.
    """
    # Get total count for pagination metadata
    total_sessions = db.query(Session).filter(
        Session.user_id == current_user.id
    ).count()
    
    # Get sessions with pagination
    sessions_query = db.query(Session).filter(
        Session.user_id == current_user.id
    ).order_by(Session.updated_at.desc())
    
    # Apply pagination
    sessions = sessions_query.offset(offset).limit(limit).all()
    
    # Load chat previews if requested
    if load_chat_previews:
        for session in sessions:
            preview_chats = db.query(Chat).filter(
                Chat.session_id == session.id
            ).order_by(Chat.created_at.desc()).limit(3).all()
            session.chats = preview_chats
    else:
        # Set empty chats list if not loading previews
        for session in sessions:
            session.chats = []
    
    # Add pagination headers
    response.headers["X-Total-Count"] = str(total_sessions)
    response.headers["X-Page-Size"] = str(limit)
    response.headers["X-Page-Offset"] = str(offset)
    response.headers["X-Has-More"] = str(offset + limit < total_sessions)
    
    logger.info(f"Loaded {len(sessions)} user sessions (offset: {offset}, limit: {limit}, total: {total_sessions}) with chat previews for user {current_user.id}")
    return sessions

@router.get("/metadata")
async def get_session_metadata(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get session metadata for the current user.
    Useful for pagination and UI state management.
    """
    total_sessions = db.query(Session).filter(
        Session.user_id == current_user.id
    ).count()
    
    latest_session = db.query(Session).filter(
        Session.user_id == current_user.id
    ).order_by(Session.updated_at.desc()).first()
    
    return {
        "total_sessions": total_sessions,
        "latest_session_id": latest_session.id if latest_session else None,
        "latest_updated_at": latest_session.updated_at if latest_session else None
    }

@router.get("/search", response_model=SessionSearchResponse)
async def search_sessions(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    response: Response,
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    search_in: Literal["prompts", "responses", "both"] = Query("both", description="What to search in"),
    limit: Optional[int] = Query(10, ge=1, le=50, description="Number of sessions to return"),
    offset: Optional[int] = Query(0, ge=0, description="Number of sessions to skip"),
    include_chat_limit: Optional[int] = Query(5, ge=1, le=20, description="Max matching chats per session")
) -> SessionSearchResponse:
    """
    Search through user's session history including prompts and responses.
    
    - q: Search query (required, 1-500 characters)
    - search_in: Search in 'prompts', 'responses', or 'both' (default: 'both')
    - limit: Number of sessions to return (default: 10, max: 50)
    - offset: Number of sessions to skip for pagination (default: 0)
    - include_chat_limit: Max matching chats to include per session (default: 5, max: 20)
    
    Returns sessions that contain matching chats, ordered by most recent match first.
    """
    logger.info(f"Searching sessions for user {current_user.id}: query='{q}', search_in='{search_in}', limit={limit}, offset={offset}")
    
    # Prepare search term (case-insensitive)
    search_term = f"%{q.lower()}%"
    
    # Build the search conditions based on search_in parameter
    search_conditions = []
    
    if search_in in ["prompts", "both"]:
        search_conditions.append(func.lower(Chat.prompt).like(search_term))
    
    if search_in in ["responses", "both"]:
        search_conditions.append(
            and_(
                Chat.response.isnot(None),
                Chat.response != "",
                func.lower(Chat.response).like(search_term)
            )
        )
    
    if not search_conditions:
        raise HTTPException(status_code=400, detail="Invalid search_in parameter")
    
    # Combine search conditions with OR
    combined_search_condition = or_(*search_conditions)
    
    # First, get all sessions that have matching chats
    sessions_with_matches_query = db.query(Session.id).join(Chat).filter(
        Session.user_id == current_user.id,
        combined_search_condition
    ).distinct()
    
    # Get total count of sessions with matches
    total_sessions_with_matches = sessions_with_matches_query.count()
    
    # Get total count of individual chat matches
    total_chat_matches = db.query(Chat).join(Session).filter(
        Session.user_id == current_user.id,
        combined_search_condition
    ).count()
    
    # Get paginated session IDs ordered by most recent matching chat
    session_ids_with_recent_match = db.query(
        Session.id,
        func.max(Chat.created_at).label('latest_match')
    ).join(Chat).filter(
        Session.user_id == current_user.id,
        combined_search_condition
    ).group_by(Session.id).order_by(
        func.max(Chat.created_at).desc()
    ).offset(offset).limit(limit).all()
    
    # Extract session IDs
    session_ids = [row[0] for row in session_ids_with_recent_match]
    
    if not session_ids:
        # No matches found
        response.headers["X-Total-Count"] = "0"
        response.headers["X-Chat-Matches"] = "0"
        response.headers["X-Has-More"] = "false"
        
        return SessionSearchResponse(
            results=[],
            total_results=0,
            total_chat_matches=0,
            has_more=False,
            query=q,
            search_in=search_in
        )
    
    # Get full session details for the paginated results
    sessions = db.query(Session).filter(
        Session.id.in_(session_ids)
    ).all()
    
    # Create a mapping for quick session lookup
    session_map = {session.id: session for session in sessions}
    
    # Get matching chats for these sessions
    matching_chats_query = db.query(Chat).filter(
        Chat.session_id.in_(session_ids),
        combined_search_condition
    ).order_by(Chat.created_at.desc())
    
    matching_chats = matching_chats_query.all()
    
    # Group chats by session and determine match types
    session_results = []
    
    for session_id in session_ids:  # Maintain order from the query
        session = session_map[session_id]
        session_chats = [chat for chat in matching_chats if chat.session_id == session_id]
        
        # Limit chats per session
        limited_chats = session_chats[:include_chat_limit]
        
        # Determine match type for each chat
        search_chats = []
        for chat in limited_chats:
            match_type = "both"  # Default
            
            prompt_matches = q.lower() in (chat.prompt or "").lower()
            response_matches = q.lower() in (chat.response or "").lower()
            
            if prompt_matches and response_matches:
                match_type = "both"
            elif prompt_matches:
                match_type = "prompt"
            elif response_matches:
                match_type = "response"
            
            search_chats.append(SessionSearchChat(
                id=chat.id,
                prompt=chat.prompt,
                response=chat.response,
                created_at=chat.created_at,
                match_type=match_type
            ))
        
        session_results.append(SessionSearchResult(
            session=SessionSearchSession(
                id=session.id,
                name=session.name,
                created_at=session.created_at,
                updated_at=session.updated_at
            ),
            matching_chats=search_chats,
            total_matches_in_session=len(session_chats)
        ))
    
    # Set response headers
    has_more = offset + limit < total_sessions_with_matches
    response.headers["X-Total-Count"] = str(total_sessions_with_matches)
    response.headers["X-Chat-Matches"] = str(total_chat_matches)
    response.headers["X-Page-Size"] = str(limit)
    response.headers["X-Page-Offset"] = str(offset)
    response.headers["X-Has-More"] = str(has_more).lower()
    
    logger.info(f"Search completed: found {total_sessions_with_matches} sessions with {total_chat_matches} total chat matches")
    
    return SessionSearchResponse(
        results=session_results,
        total_results=total_sessions_with_matches,
        total_chat_matches=total_chat_matches,
        has_more=has_more,
        query=q,
        search_in=search_in
    ) 