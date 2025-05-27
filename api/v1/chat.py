from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import uuid
# import requests # No longer needed for the streaming part
import json
# import asyncio # No longer needed directly in stream_response
import httpx
from datetime import datetime, timedelta

from app.core.config import settings
from app.db.base import get_db
from app.models.chat import Chat
from app.models.session import Session as DBSession # Renamed to avoid conflict with sqlalchemy.orm.Session
from app.schemas.chat import ChatCreate, Chat as ChatSchema
from app.api.v1.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])

# [NEW] Added on 2024-03-21: Function to update chat in database as chunks arrive
async def update_chat_in_db(db: Session, chat_id: str, chunk_text: str):
    """Update chat response in database with a text chunk.
       Note: Frequent commits can impact DB performance. Consider accumulating.
    """
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if chat:
        chat.response = (chat.response or "") + chunk_text
        db.add(chat)
        db.commit()

# [NEW] Added on 2024-03-21: Function to handle streaming errors
async def handle_streaming_error(db: Session, chat_id: str, error: Exception):
    """Handle streaming errors by updating the chat response in the database."""
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if chat:
        base_response = chat.response or ""
        if base_response and not base_response.endswith(("\n", "\n\n")):
            base_response += "\n\n"
        error_message = f"Error occurred during streaming: {str(error)}"
        # Avoid duplicating error messages if called multiple times for the same error.
        if error_message not in base_response:
            chat.response = f"{base_response}{error_message}"
            db.add(chat)
            db.commit()

# [MODIFIED] Updated on 2024-03-21: Enhanced stream_response function
async def stream_response(response: httpx.Response, db: Session, chat_id: str):
    """
    Helper function to stream SSE events from the external service,
    update the database accordingly, and forward events to the client.
    """
    accumulated_text_for_db_response = ""
    try:
        async for line in response.aiter_lines():
            # print(f"[DEBUG CHAT.PY] Received line: {line}")
            if line.startswith("data:"):
                json_payload_str = line[len("data:"):].strip()
                if not json_payload_str:  # Skip empty data lines (e.g. keep-alives from upstream)
                    if line == "data:": # an empty data field is valid sse, forward it.
                         yield f"{line}\n\n"
                    continue

                try:
                    # This is the payload from app_stream.py, e.g.,
                    # {'type': 'metadata', 'metadata': {...}} or
                    # {'type': 'content', 'content': 'text chunk'} or
                    # {'type': 'done', ...}
                    payload_from_external = json.loads(json_payload_str)

                    # Forward the original, correctly formatted SSE line to our client
                    yield f"{line}\n\n"  # Ensure proper SSE event termination

                    # Process the payload for database updates
                    event_type = payload_from_external.get('type')
                    
                    if event_type == 'metadata':
                        metadata_content = payload_from_external.get('metadata')
                        if metadata_content:
                            chat = db.query(Chat).filter(Chat.id == chat_id).first()
                            if chat:
                                # Update fields from metadata
                                if 'phones' in metadata_content:
                                    chat.phones = metadata_content['phones']
                                if 'current_params' in metadata_content:
                                    chat.current_params = metadata_content['current_params']
                                if 'button_text' in metadata_content:
                                    chat.button_text = metadata_content.get('button_text', chat.button_text)
                                # Add other metadata fields as needed e.g.
                                # if 'query_type' in metadata_content: chat.query_type = metadata_content['query_type']
                                db.add(chat)
                                db.commit()

                    elif event_type == 'content':
                        content_chunk = payload_from_external.get('content')
                        if content_chunk and isinstance(content_chunk, str):
                            accumulated_text_for_db_response += content_chunk
                            # Optional: Update DB per chunk.
                            # await update_chat_in_db(db, chat_id, content_chunk)
                    
                    elif event_type == 'done':
                        # The 'done' event from app_stream.py might contain the full text.
                        # If we haven't built it from 'content' chunks, we can use this.
                        full_text_from_done = payload_from_external.get('full_text')
                        if full_text_from_done and not accumulated_text_for_db_response:
                             accumulated_text_for_db_response = full_text_from_done
                        # Process other 'done' event data if necessary

                except json.JSONDecodeError as e_json:
                    print(f"[ERROR CHAT.PY] stream_response - JSONDecodeError for payload: '{json_payload_str}'. Error: {e_json}")
                    # Forward an error specific to this malformed data chunk
                    error_event = {'type': 'error', 'content': f'Malformed data from upstream: {json_payload_str[:100]}...'}
                    yield f"data: {json.dumps(error_event)}\n\n"
                except Exception as e_process:
                    print(f"[ERROR CHAT.PY] stream_response - Error processing payload: '{json_payload_str}'. Error: {e_process}")
                    await handle_streaming_error(db, chat_id, e_process)
                    error_event = {'type': 'error', 'content': f'Error processing upstream data: {str(e_process)}'}
                    yield f"data: {json.dumps(error_event)}\n\n"

            elif line.strip() and not line.startswith(":"): # Forward other SSE lines (event, id, retry) but not comments
                yield f"{line}\n" # SSE spec says these lines end with a single \n before the final \n\n
            elif line.strip().startswith(":"): # SSE comment
                yield f"{line}\n" # Forward comments as well
            elif not line.strip(): # An empty line signifies end of an event
                pass # aiter_lines gives us individual lines; we add \n\n for "data:" lines

        # After iterating through all lines, update the DB with the full accumulated response.
        if accumulated_text_for_db_response:
            chat = db.query(Chat).filter(Chat.id == chat_id).first()
            if chat:
                chat.response = accumulated_text_for_db_response
                db.add(chat)
                db.commit()

    except httpx.ReadTimeout as e_timeout:
        print(f"[ERROR CHAT.PY] stream_response - ReadTimeout from external service for chat_id: {chat_id}. Error: {e_timeout}")
        err = TimeoutError(f"Timeout receiving data from the recommendation service: {e_timeout}")
        await handle_streaming_error(db, chat_id, err)
        error_event = {'type': 'error', 'content': str(err)}
        yield f"data: {json.dumps(error_event)}\n\n"
    except Exception as e_outer:
        print(f"[ERROR CHAT.PY] stream_response - General streaming error for chat_id: {chat_id}. Error: {e_outer}")
        await handle_streaming_error(db, chat_id, e_outer)
        error_event = {'type': 'error', 'content': f'Stream processing error: {str(e_outer)}'}
        yield f"data: {json.dumps(error_event)}\n\n"


# [MODIFIED] Streaming wrapper
async def stream_response_wrapper(url: str, json_payload: dict, db: Session, chat_id: str):
    # Note: httpx.AsyncClient should ideally be managed globally or per-app for performance
    # rather than created on each request, but for simplicity here it's per-call.
    async with httpx.AsyncClient() as client:
        try:
            async with client.stream(
                'POST',
                url,
                json=json_payload,
                timeout=settings.STREAMING_TIMEOUT
            ) as response:
                response.raise_for_status()  # Check for HTTP errors (4xx, 5xx) before streaming
                async for chunk_to_forward in stream_response(response, db, chat_id):
                    yield chunk_to_forward
        except httpx.HTTPStatusError as e_http_status:
            print(f"[ERROR CHAT.PY] stream_response_wrapper - HTTPStatusError: {e_http_status.request.url} - Status {e_http_status.response.status_code}")
            await handle_streaming_error(db, chat_id, e_http_status)
            error_content = f'External service error: {e_http_status.response.status_code}'
            try: # Try to get more details from response if JSON
                error_details = e_http_status.response.json()
                error_content += f" - {json.dumps(error_details)}"
            except json.JSONDecodeError:
                error_content += f" - {e_http_status.response.text[:200]}" # First 200 chars of text response

            yield f"data: {json.dumps({'type': 'error', 'content': error_content})}\n\n"
        except httpx.RequestError as e_request: # Covers network errors, DNS failures, timeouts before response, etc.
            print(f"[ERROR CHAT.PY] stream_response_wrapper - RequestError: {e_request.request.url} - {e_request}")
            await handle_streaming_error(db, chat_id, e_request)
            yield f"data: {json.dumps({'type': 'error', 'content': f'Error connecting to external service: {str(e_request)}'})}\n\n"
        except Exception as e_unexpected:
            print(f"[ERROR CHAT.PY] stream_response_wrapper - Unexpected error: {e_unexpected}")
            await handle_streaming_error(db, chat_id, e_unexpected)
            yield f"data: {json.dumps({'type': 'error', 'content': f'An unexpected error occurred: {str(e_unexpected)}'})}\n\n"


@router.post("", response_model=None)
async def create_chat(
    *,
    db: Session = Depends(get_db),
    chat_in: ChatCreate,
    current_user: User = Depends(get_current_user)
) -> StreamingResponse:
    """
    Create a new chat session with the first message. Streams response.
    """
    recent_time = datetime.utcnow() - timedelta(minutes=2)
    recent_db_session = db.query(DBSession).filter(
        DBSession.user_id == current_user.id,
        DBSession.created_at >= recent_time
    ).order_by(DBSession.created_at.desc()).first()

    if not recent_db_session:
        # Create new session if none exists
        recent_db_session = DBSession(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            name="New Chat Session"
        )
        db.add(recent_db_session)
        db.commit()
        db.refresh(recent_db_session)

    # Create new chat entry
    chat = Chat(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        session_id=recent_db_session.id,
        prompt=chat_in.prompt,
        current_params=chat_in.current_params or {}
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)

    # Get chat history for context
    chat_history = db.query(Chat).filter(
        Chat.session_id == recent_db_session.id
    ).order_by(Chat.created_at.asc()).all()

    # Prepare chat history for the processing layer
    history_context = [
        {"role": "user", "content": c.prompt} for c in chat_history
    ]
    if chat_history:
        history_context.extend([
            {"role": "assistant", "content": c.response} 
            for c in chat_history if c.response
        ])

    # Add current message
    history_context.append({"role": "user", "content": chat_in.prompt})

    # Prepare payload with history
    json_payload = {
        "prompt": chat_in.prompt,
        "current_params": chat_in.current_params or {},
        "chat_history": history_context
    }

    return StreamingResponse(
        stream_response_wrapper(
            settings.MICRO_URL,
            json_payload,
            db,
            chat.id
        ),
        media_type="text/event-stream"
    )

@router.post("/{session_id}", response_model=None)
async def continue_chat(
    *,
    db: Session = Depends(get_db),
    session_id: str,
    chat_in: ChatCreate,
    current_user: User = Depends(get_current_user)
) -> StreamingResponse:
    """
    Continue an existing chat session with a new message. Streams response.
    """
    # Verify session exists and belongs to user
    session = db.query(DBSession).filter(
        DBSession.id == session_id,
        DBSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Create new chat entry
    chat = Chat(
        id=str(uuid.uuid4()),
        user_id=current_user.id,
        session_id=session_id,
        prompt=chat_in.prompt,
        current_params=chat_in.current_params or {}
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)

    # Get chat history for context
    chat_history = db.query(Chat).filter(
        Chat.session_id == session_id
    ).order_by(Chat.created_at.asc()).all()

    # Prepare chat history for the processing layer
    history_context = [
        {"role": "user", "content": c.prompt} for c in chat_history
    ]
    if chat_history:
        history_context.extend([
            {"role": "assistant", "content": c.response} 
            for c in chat_history if c.response
        ])

    # Add current message
    history_context.append({"role": "user", "content": chat_in.prompt})

    # Prepare payload with history
    json_payload = {
        "prompt": chat_in.prompt,
        "current_params": chat_in.current_params or {},
        "chat_history": history_context
    }

    return StreamingResponse(
        stream_response_wrapper(
            settings.MICRO_URL,
            json_payload,
            db,
            chat.id
        ),
        media_type="text/event-stream"
    )

@router.get("/user/history", response_model=List[ChatSchema])
async def get_user_chat_history(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get all chat history for the current user
    """
    chats = db.query(Chat).filter(Chat.user_id == current_user.id).order_by(Chat.created_at.desc()).all()
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
    db_session = db.query(DBSession).filter(DBSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Session not found")
    if db_session.user_id != current_user.id and not db_session.is_public: # Allow access if session is public
         raise HTTPException(status_code=403, detail="Not authorized to view this session's history")
    
    chats = db.query(Chat).filter(
        Chat.session_id == session_id
    ).order_by(Chat.created_at).all() # Order by creation time for chronological history
    return chats
