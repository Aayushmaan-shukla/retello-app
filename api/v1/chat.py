'''from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import uuid
import requests
import json
import asyncio
import httpx
from datetime import datetime, timedelta

from app.core.config import settings
from app.db.base import get_db
from app.models.chat import Chat
from app.models.session import Session
from app.schemas.chat import ChatCreate, Chat as ChatSchema
from app.api.v1.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])

async def stream_response(response):
    """Helper function to stream the response from the external service"""
    async for chunk in response.aiter_text():
        if chunk:
            yield f"data: {chunk}\n\n"
            await asyncio.sleep(0.01)

@router.post("", response_model=ChatSchema)
async def create_chat(
    *,
    db: Session = Depends(get_db),
    chat_in: ChatCreate,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Create a new chat session with the first message.
    This endpoint is used for the first message in a conversation.
    """
    # Check for a recent session (within the last 2 minutes)
    recent_time = datetime.utcnow() - timedelta(minutes=2)
    recent_session = db.query(Session).filter(
        Session.user_id == current_user.id,
        Session.created_at >= recent_time
    ).order_by(Session.created_at.desc()).first()

    if recent_session:
        db_session = recent_session
        session_id = db_session.id
    else:
        db_session = Session(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            name=f"Chat Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            is_public=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(db_session)
        db.commit()
        session_id = db_session.id

    # Prepare prompt for external service
    prompt = {
        "user_input": chat_in.prompt,
        "conversation": [
            {
                "role": "system",
                "content": "You are an intelligent phone recommendation assistant by a company called \"Retello\"\nAvailable features and their descriptions:\n{\n  \"battery_capacity\": \"Battery size in mAh\",\n  \"main_camera\": \"Main camera resolution in MP\",\n  \"front_camera\": \"Front camera resolution in MP\",\n  \"screen_size\": \"Screen size in inches\",\n  \"charging_speed\": \"Charging speed in watts\",\n  \"os\": \"Android version\",\n  \"camera_count\": \"Number of cameras\",\n  \"sensors\": \"Available sensors\",\n  \"display_type\": \"Display technology\",\n  \"network\": \"Network connectivity\",\n  \"chipset\": \"processor/chipset name\",\n  \"preferred_brands\": \"names of the brands preferred by a user\",\n  \"price_range\": \"price a user is willing to pay\"\n}\n\nMap user requirements to these specific features if possible. Consider both explicit and implicit needs."
            },
            {"role": "user", "content": chat_in.prompt}
        ]
    }

    # Call external service with streaming
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.MICRO_URL,
                json=prompt,
                timeout=None
            )
            response.raise_for_status()
            
            # Create chat entry with initial data
            response_data = response.json()
            db_chat = Chat(
                id=str(uuid.uuid4()),
                user_id=current_user.id,
                session_id=session_id,
                prompt=chat_in.prompt,
                response="",  # Will be updated as we receive chunks
                phones=[],    # Will be updated as we receive chunks
                current_params={},  # Will be updated as we receive chunks
                button_text=response_data.get("button_text", "See more")  # Add button_text
            )
            db.add(db_chat)
            db.commit()
            
            return StreamingResponse(
                stream_response(response),
                media_type="text/event-stream"
            )
            
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Error calling external service: {str(e)}")

    # # Old non-streaming implementation
    # try:
    #     response = requests.post(settings.MICRO_URL, json=prompt)
    #     response.raise_for_status()
    #     response_data = response.json()
    # except requests.RequestException as e:
    #     raise HTTPException(status_code=500, detail=f"Error calling external service: {str(e)}")

    # # Create chat entry
    # db_chat = Chat(
    #     id=str(uuid.uuid4()),
    #     user_id=current_user.id,
    #     session_id=session_id,
    #     prompt=chat_in.prompt,
    #     response=response_data.get("follow_up_question", [{}])[-1].get("content"),
    #     phones=response_data.get("phones", []),
    #     current_params=response_data.get("current_params", {})
    # )
    # db.add(db_chat)
    # db.commit()
    # db.refresh(db_chat)
    # return db_chat

@router.post("/{session_id}", response_model=ChatSchema)
async def continue_chat(
    *,
    db: Session = Depends(get_db),
    session_id: str,
    chat_in: ChatCreate,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Continue an existing chat session.
    This endpoint is used for all messages after the first one in a conversation.
    """
    # Check session exists and permissions
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to chat in this session"
        )

    # Update session's updated_at timestamp
    session.updated_at = datetime.utcnow()
    db.add(session)

    # Get previous chats
    prev_chats = db.query(Chat).filter(Chat.session_id == session_id).all()
    formatted_chats = []
    for chat in prev_chats:
        formatted_chats.extend([
            {"role": "user", "content": chat.prompt},
            {"role": "assistant", "content": chat.response or "I am sorry, I don't have a response for that."}
        ])

    # Prepare prompt for external service
    prompt = {
        "user_input": chat_in.prompt
    }
    
    if formatted_chats:
        last_chat = prev_chats[-1] if prev_chats else None
        prompt.update({
            "current_params": last_chat.current_params if last_chat else None,
            "conversation": [
                {
                    "role": "system",
                    "content": "You are an intelligent phone recommendation assistant by a company called \"Retello\"\nAvailable features and their descriptions:\n{\n  \"battery_capacity\": \"Battery size in mAh\",\n  \"main_camera\": \"Main camera resolution in MP\",\n  \"front_camera\": \"Front camera resolution in MP\",\n  \"screen_size\": \"Screen size in inches\",\n  \"charging_speed\": \"Charging speed in watts\",\n  \"os\": \"Android version\",\n  \"camera_count\": \"Number of cameras\",\n  \"sensors\": \"Available sensors\",\n  \"display_type\": \"Display technology\",\n  \"network\": \"Network connectivity\",\n  \"chipset\": \"processor/chipset name\",\n  \"preferred_brands\": \"names of the brands preferred by a user\",\n  \"price_range\": \"price a user is willing to pay\"\n}\n\nMap user requirements to these specific features if possible. Consider both explicit and implicit needs."
                },
                *formatted_chats,
                {"role": "user", "content": chat_in.prompt}
            ]
        })

    # Call external service with streaming
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.MICRO_URL,
                json=prompt,
                timeout=None
            )
            response.raise_for_status()
            
            # Create chat entry with initial data
            response_data = response.json()
            db_chat = Chat(
                id=str(uuid.uuid4()),
                user_id=current_user.id,
                session_id=session_id,
                prompt=chat_in.prompt,
                response="",  # Will be updated as we receive chunks
                phones=[],    # Will be updated as we receive chunks
                current_params={},  # Will be updated as we receive chunks
                button_text=response_data.get("button_text", "See more")  # Add button_text
            )
            db.add(db_chat)
            db.commit()
            
            return StreamingResponse(
                stream_response(response),
                media_type="text/event-stream"
            )
            
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Error calling external service: {str(e)}")

    # # Old non-streaming implementation
    # try:
    #     response = requests.post(settings.MICRO_URL, json=prompt)
    #     response.raise_for_status()
    #     response_data = response.json()
    # except requests.RequestException as e:
    #     raise HTTPException(status_code=500, detail=f"Error calling external service: {str(e)}")

    # # Create chat entry
    # db_chat = Chat(
    #     id=str(uuid.uuid4()),
    #     user_id=current_user.id,
    #     session_id=session_id,
    #     prompt=chat_in.prompt,
    #     response=response_data.get("follow_up_question", [{}])[-1].get("content"),
    #     phones=response_data.get("phones", []),
    #     current_params=response_data.get("current_params", {})
    # )
    # db.add(db_chat)
    # db.commit()
    # db.refresh(db_chat)
    # return db_chat

@router.get("/user/history", response_model=List[ChatSchema])
async def get_user_chat_history(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get all chat history for the current user
    """
    chats = db.query(Chat).filter(Chat.user_id == current_user.id).all()
    return chats

@router.get("/session/{session_id}/history", response_model=List[ChatSchema])
async def get_session_chat_history(
    *,
    db: Session = Depends(get_db),
    session_id: str,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get chat history for a specific session
    """
    # Check if session exists and belongs to user
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this session's history")
    
    chats = db.query(Chat).filter(
        Chat.session_id == session_id,
        Chat.user_id == current_user.id
    ).all()
    return chats '''
from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid
import requests
from datetime import datetime

from app.core.config import settings
from app.db.base import get_db
from app.models.chat import Chat
from app.models.session import Session
from app.schemas.chat import ChatCreate, Chat as ChatSchema
from app.api.v1.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("", response_model=ChatSchema)
async def create_chat(
    *,
    db: Session = Depends(get_db),
    chat_in: ChatCreate,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Create a new chat session with the first message.
    This endpoint is used for the first message in a conversation.
    """
    # Create new session for first message
    db_session = Session(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        name=f"Chat Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        is_public=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(db_session)
    db.commit()
    session_id = db_session.id

    # Prepare prompt for external service
    prompt = {
        "user_input": chat_in.prompt,
        "conversation": [
            {
                "role": "system",
                "content": "You are an intelligent phone recommendation assistant by a company called \"Retello\"\nAvailable features and their descriptions:\n{\n  \"battery_capacity\": \"Battery size in mAh\",\n  \"main_camera\": \"Main camera resolution in MP\",\n  \"front_camera\": \"Front camera resolution in MP\",\n  \"screen_size\": \"Screen size in inches\",\n  \"charging_speed\": \"Charging speed in watts\",\n  \"os\": \"Android version\",\n  \"camera_count\": \"Number of cameras\",\n  \"sensors\": \"Available sensors\",\n  \"display_type\": \"Display technology\",\n  \"network\": \"Network connectivity\",\n  \"chipset\": \"processor/chipset name\",\n  \"preferred_brands\": \"names of the brands preferred by a user\",\n  \"price_range\": \"price a user is willing to pay\"\n}\n\nMap user requirements to these specific features if possible. Consider both explicit and implicit needs."
            },
            {"role": "user", "content": chat_in.prompt}
        ]
    }

    # Call external service
    try:
        response = requests.post(settings.MICRO_URL, json=prompt)
        response.raise_for_status()
        response_data = response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error calling external service: {str(e)}")

    button_text = response_data.get("button_text", "See more")

    db_chat = Chat(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        session_id=session_id,
        prompt=chat_in.prompt,
        response=response_data.get("follow_up_question", [{}])[-1].get("content"),
        phones=response_data.get("phones", []),
        current_params=response_data.get("current_params", {}),
        button_text=button_text
    )
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)
    return {
        **db_chat.__dict__,
        "button_text": button_text
    }

@router.post("/{session_id}", response_model=ChatSchema)
async def continue_chat(
    *,
    db: Session = Depends(get_db),
    session_id: str,
    chat_in: ChatCreate,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Continue an existing chat session.
    This endpoint is used for all messages after the first one in a conversation.
    """
    # Check session exists and permissions
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to chat in this session"
        )

    # Update session's updated_at timestamp
    session.updated_at = datetime.utcnow()
    db.add(session)

    # Get previous chats
    prev_chats = db.query(Chat).filter(Chat.session_id == session_id).all()
    formatted_chats = []
    for chat in prev_chats:
        formatted_chats.extend([
            {"role": "user", "content": chat.prompt},
            {"role": "assistant", "content": chat.response or "I am sorry, I don't have a response for that."}
        ])

    # Prepare prompt for external service
    prompt = {
        "user_input": chat_in.prompt
    }
    
    if formatted_chats:
        last_chat = prev_chats[-1] if prev_chats else None
        prompt.update({
            "current_params": last_chat.current_params if last_chat else None,
            "conversation": [
                {
                    "role": "system",
                    "content": "You are an intelligent phone recommendation assistant by a company called \"Retello\"\nAvailable features and their descriptions:\n{\n  \"battery_capacity\": \"Battery size in mAh\",\n  \"main_camera\": \"Main camera resolution in MP\",\n  \"front_camera\": \"Front camera resolution in MP\",\n  \"screen_size\": \"Screen size in inches\",\n  \"charging_speed\": \"Charging speed in watts\",\n  \"os\": \"Android version\",\n  \"camera_count\": \"Number of cameras\",\n  \"sensors\": \"Available sensors\",\n  \"display_type\": \"Display technology\",\n  \"network\": \"Network connectivity\",\n  \"chipset\": \"processor/chipset name\",\n  \"preferred_brands\": \"names of the brands preferred by a user\",\n  \"price_range\": \"price a user is willing to pay\"\n}\n\nMap user requirements to these specific features if possible. Consider both explicit and implicit needs."
                },
                *formatted_chats,
                {"role": "user", "content": chat_in.prompt}
            ]
        })

    # Call external service
    try:
        response = requests.post(settings.MICRO_URL, json=prompt)
        response.raise_for_status()
        response_data = response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error calling external service: {str(e)}")

    button_text = response_data.get("button_text", "See more")

    db_chat = Chat(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        session_id=session_id,
        prompt=chat_in.prompt,
        response=response_data.get("follow_up_question", [{}])[-1].get("content"),
        phones=response_data.get("phones", []),
        current_params=response_data.get("current_params", {}),
        button_text=button_text
    )
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)
    return {
        **db_chat.__dict__,
        "button_text": button_text
    }

@router.get("/user/history", response_model=List[ChatSchema])
async def get_user_chat_history(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get all chat history for the current user
    """
    chats = db.query(Chat).filter(Chat.user_id == current_user.id).all()
    return chats

@router.get("/session/{session_id}/history", response_model=List[ChatSchema])
async def get_session_chat_history(
    *,
    db: Session = Depends(get_db),
    session_id: str,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get chat history for a specific session
    """
    # Check if session exists and belongs to user
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this session's history")
    
    chats = db.query(Chat).filter(
        Chat.session_id == session_id,
        Chat.user_id == current_user.id
    ).all()
    return chats 
    
