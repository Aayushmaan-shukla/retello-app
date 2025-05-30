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
import logging

from app.core.config import settings
from app.db.base import get_db
from app.models.chat import Chat
from app.models.session import Session as DBSession # Renamed to avoid conflict with sqlalchemy.orm.Session
from app.schemas.chat import ChatCreate, Chat as ChatSchema
from app.api.v1.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("chat")

# [NEW] Added on 2024-03-21: Function to update chat in database as chunks arrive
async def update_chat_in_db(db: Session, chat_id: str, chunk_text: str):
    """Update chat response in database with a text chunk.
       Note: Frequent commits can impact DB performance. Consider accumulating.
    """
    try:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if chat:
            chat.response = (chat.response or "") + chunk_text
            db.add(chat)
            db.commit()
            logger.debug(f"Updated chat {chat_id} with new chunk")
        else:
            logger.warning(f"Chat {chat_id} not found for update")
    except Exception as e:
        logger.error(f"Error updating chat {chat_id} in database: {str(e)}")
        raise

# [NEW] Added on 2024-03-21: Function to handle streaming errors
async def handle_streaming_error(db: Session, chat_id: str, error: Exception):
    """Handle streaming errors by updating the chat response in the database."""
    logger.error(f"Streaming error for chat {chat_id}: {str(error)}")
    try:
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
                logger.info(f"Updated chat {chat_id} with error message")
        else:
            logger.warning(f"Chat {chat_id} not found for error handling")
    except Exception as e:
        logger.error(f"Error handling streaming error for chat {chat_id}: {str(e)}")

# [MODIFIED] Updated on 2024-03-21: Enhanced stream_response function
async def stream_response(response: httpx.Response, db: Session, chat_id: str):
    """
    Helper function to stream SSE events from the external service,
    update the database accordingly, and forward events to the client.
    """
    logger.info(f"Starting stream response for chat {chat_id}")
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
                            logger.debug(f"Processing metadata for chat {chat_id}: {metadata_content}")
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
                                logger.info(f"Updated chat {chat_id} with metadata")

                    elif event_type == 'content':
                        content_chunk = payload_from_external.get('content')
                        if content_chunk and isinstance(content_chunk, str):
                            accumulated_text_for_db_response += content_chunk
                            logger.debug(f"Accumulated content chunk for chat {chat_id}")
                            # Optional: Update DB per chunk.
                            # await update_chat_in_db(db, chat_id, content_chunk)
                    
                    elif event_type == 'done':
                        # The 'done' event from app_stream.py might contain the full text.
                        # If we haven't built it from 'content' chunks, we can use this.
                        full_text_from_done = payload_from_external.get('full_text')
                        if full_text_from_done and not accumulated_text_for_db_response:
                             accumulated_text_for_db_response = full_text_from_done
                        logger.info(f"Received done event for chat {chat_id}")
                        # Process other 'done' event data if necessary

                except json.JSONDecodeError as e_json:
                    logger.error(f"JSON decode error for chat {chat_id}: {str(e_json)}")
                    # Forward an error specific to this malformed data chunk
                    error_event = {'type': 'error', 'content': f'Malformed data from upstream: {json_payload_str[:100]}...'}
                    yield f"data: {json.dumps(error_event)}\n\n"
                except Exception as e_process:
                    logger.error(f"Error processing payload for chat {chat_id}: {str(e_process)}")
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
            logger.info(f"Updating final response for chat {chat_id}")
            chat = db.query(Chat).filter(Chat.id == chat_id).first()
            if chat:
                chat.response = accumulated_text_for_db_response
                db.add(chat)
                db.commit()
                logger.info(f"Final response updated for chat {chat_id}")

    except httpx.ReadTimeout as e_timeout:
        logger.error(f"Timeout error for chat {chat_id}: {str(e_timeout)}")
        err = TimeoutError(f"Timeout receiving data from the recommendation service: {e_timeout}")
        await handle_streaming_error(db, chat_id, err)
        error_event = {'type': 'error', 'content': str(err)}
        yield f"data: {json.dumps(error_event)}\n\n"
    except Exception as e_outer:
        logger.error(f"General streaming error for chat {chat_id}: {str(e_outer)}")
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


@router.post("", response_model=None) # response_model=ChatSchema is misleading for StreamingResponse
async def create_chat(
    *,
    db: Session = Depends(get_db),
    chat_in: ChatCreate,
    current_user: User = Depends(get_current_user)
) -> StreamingResponse:
    """
    Create a new chat session with the first message. Streams response.
    """
    logger.info(f"Creating new chat for user {current_user.id}")
    
    if not chat_in.prompt:
        logger.warning(f"Missing prompt in chat creation request for user {current_user.id}")
        raise HTTPException(status_code=400, detail="'prompt' field is required")

    try:
        recent_time = datetime.utcnow() - timedelta(minutes=2)
        recent_db_session = db.query(DBSession).filter(
            DBSession.user_id == current_user.id,
            DBSession.created_at >= recent_time
        ).order_by(DBSession.created_at.desc()).first()

        if recent_db_session:
            session_id = recent_db_session.id
            logger.info(f"Using existing session {session_id} for user {current_user.id}")
            
            # Get previous chats from this session for context
            prev_chats = db.query(Chat).filter(Chat.session_id == session_id).order_by(Chat.created_at).all()
            formatted_chats = []
            for chat_item in prev_chats:
                formatted_chats.extend([
                    {"role": "user", "content": chat_item.prompt},
                    {"role": "assistant", "content": chat_item.response or "I am sorry, I don't have a response for that."}
                ])
            
            logger.info(f"Including {len(prev_chats)} previous chats for context in session {session_id}")
            
        else:
            new_db_session = DBSession(
                id=str(uuid.uuid4()),
                user_id=current_user.id,
                name=f"Chat Session {datetime.now().strftime('%Y-%m-%d %H:%M')}", # Consider UTC if consistency is key
                is_public=False,
                created_at=datetime.utcnow(), # Ensure this is UTC
                updated_at=datetime.utcnow()  # Ensure this is UTC
            )
            db.add(new_db_session)
            db.commit() # Commit session first to ensure session_id is valid
            session_id = new_db_session.id
            formatted_chats = []  # No previous chats for new session
            logger.info(f"Created new session {session_id} for user {current_user.id}")

        # Build conversation with history if available
        conversation = [
            {
                "role": "system",
                "content": "You are an intelligent phone recommendation assistant by a company called \"Retello\"\nAvailable features and their descriptions:\n{\n  \"battery_capacity\": \"Battery size in mAh\",\n  \"main_camera\": \"Main camera resolution in MP\",\n  \"front_camera\": \"Front camera resolution in MP\",\n  \"screen_size\": \"Screen size in inches\",\n  \"charging_speed\": \"Charging speed in watts\",\n  \"os\": \"Android version\",\n  \"camera_count\": \"Number of cameras\",\n  \"sensors\": \"Available sensors\",\n  \"display_type\": \"Display technology\",\n  \"network\": \"Network connectivity\",\n  \"chipset\": \"processor/chipset name\",\n  \"preferred_brands\": \"names of the brands preferred by a user\",\n  \"price_range\": \"price a user is willing to pay\"\n}\n\nMap user requirements to these specific features if possible. Consider both explicit and implicit needs."
            }
        ]
        
        # Add previous conversation history if available
        if formatted_chats:
            conversation.extend(formatted_chats)
        
        # Add current user input
        conversation.append({"role": "user", "content": chat_in.prompt})

        prompt_payload = {
            "user_input": chat_in.prompt,
            "conversation": conversation
        }
        
        # Include current_params from last chat if available
        if recent_db_session:
            last_chat = db.query(Chat).filter(Chat.session_id == session_id).order_by(Chat.created_at.desc()).first()
            if last_chat and last_chat.current_params:
                prompt_payload["current_params"] = last_chat.current_params
                logger.info(f"Including current_params from last chat in session {session_id}")

        chat_id = str(uuid.uuid4())
        logger.info(f"Creating new chat {chat_id} in session {session_id}")
        db_chat = Chat(
            id=chat_id,
            user_id=current_user.id,
            session_id=session_id,
            prompt=chat_in.prompt,
            response="",
            phones=[],
            current_params={},
            button_text="See more", # Default value
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(db_chat)
        db.commit() # Commit chat entry so stream_response can find it

        logger.info(f"Starting streaming response for chat {chat_id} with {len(conversation)-2} previous messages")
        return StreamingResponse(
            stream_response_wrapper(settings.MICRO_URL, prompt_payload, db, chat_id),
            media_type="text/event-stream"
        )

    except Exception as e:
        logger.error(f"Error creating chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating chat: {str(e)}")

@router.post("/{session_id}", response_model=None) # response_model=ChatSchema is misleading for StreamingResponse
async def continue_chat(
    *,
    db: Session = Depends(get_db),
    session_id: str,
    chat_in: ChatCreate,
    current_user: User = Depends(get_current_user)
) -> StreamingResponse:
    """
    Continue an existing chat session. Streams response.
    """
    logger.info(f"Fetching session {session_id} for user {current_user.id}")
    db_session = db.query(DBSession).filter(DBSession.id == session_id).first()
    if not db_session:
        logger.warning(f"Session {session_id} not found for user {current_user.id}")
        raise HTTPException(status_code=404, detail="Session not found")
    if db_session.user_id != current_user.id:
        logger.warning(f"Unauthorized access attempt to session {session_id} by user {current_user.id}")
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to chat in this session"
        )

    db_session.updated_at = datetime.utcnow()
    db.add(db_session) # Handled by commit below with chat

    prev_chats = db.query(Chat).filter(Chat.session_id == session_id).order_by(Chat.created_at).all() # Order to maintain conversation
    formatted_chats = []
    for chat_item in prev_chats:
        formatted_chats.extend([
            {"role": "user", "content": chat_item.prompt},
            {"role": "assistant", "content": chat_item.response or "I am sorry, I don't have a response for that."}
        ])

    prompt_payload = {
        "user_input": chat_in.prompt
    }
    
    if formatted_chats:
        last_chat = prev_chats[-1] if prev_chats else None
        prompt_payload.update({
            "current_params": last_chat.current_params if last_chat and last_chat.current_params else None, # Ensure current_params is not None if last_chat exists but has no params
            "conversation": [
                {
                    "role": "system",
                    "content": "You are an intelligent phone recommendation assistant by a company called \"Retello\"\nAvailable features and their descriptions:\n{\n  \"battery_capacity\": \"Battery size in mAh\",\n  \"main_camera\": \"Main camera resolution in MP\",\n  \"front_camera\": \"Front camera resolution in MP\",\n  \"screen_size\": \"Screen size in inches\",\n  \"charging_speed\": \"Charging speed in watts\",\n  \"os\": \"Android version\",\n  \"camera_count\": \"Number of cameras\",\n  \"sensors\": \"Available sensors\",\n  \"display_type\": \"Display technology\",\n  \"network\": \"Network connectivity\",\n  \"chipset\": \"processor/chipset name\",\n  \"preferred_brands\": \"names of the brands preferred by a user\",\n  \"price_range\": \"price a user is willing to pay\"\n}\n\nMap user requirements to these specific features if possible. Consider both explicit and implicit needs."
                },
                *formatted_chats,
                {"role": "user", "content": chat_in.prompt}
            ]
        })
    else: # If no previous chats, it's like a new chat but in an existing session
        prompt_payload.update({
            "conversation": [
                {
                    "role": "system",
                    "content": "You are an intelligent phone recommendation assistant by a company called \"Retello\"\nAvailable features and their descriptions:\n{\n  \"battery_capacity\": \"Battery size in mAh\",\n  \"main_camera\": \"Main camera resolution in MP\",\n  \"front_camera\": \"Front camera resolution in MP\",\n  \"screen_size\": \"Screen size in inches\",\n  \"charging_speed\": \"Charging speed in watts\",\n  \"os\": \"Android version\",\n  \"camera_count\": \"Number of cameras\",\n  \"sensors\": \"Available sensors\",\n  \"display_type\": \"Display technology\",\n  \"network\": \"Network connectivity\",\n  \"chipset\": \"processor/chipset name\",\n  \"preferred_brands\": \"names of the brands preferred by a user\",\n  \"price_range\": \"price a user is willing to pay\"\n}\n\nMap user requirements to these specific features if possible. Consider both explicit and implicit needs."
                },
                {"role": "user", "content": chat_in.prompt}
            ]
        })

    chat_id = str(uuid.uuid4())
    logger.info(f"Creating new chat {chat_id} in session {session_id}")
    db_chat = Chat(
        id=chat_id,
        user_id=current_user.id,
        session_id=session_id,
        prompt=chat_in.prompt,
        response="",
        phones=[],
        current_params={},
        button_text="See more", # Default value
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(db_chat)
    db.commit() # Commit chat entry and session update

    return StreamingResponse(
        stream_response_wrapper(settings.MICRO_URL, prompt_payload, db, chat_id),
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
    logger.info(f"Fetching chat history for user {current_user.id}")
    try:
        chats = db.query(Chat).filter(Chat.user_id == current_user.id).order_by(Chat.created_at.desc()).all()
        logger.info(f"Retrieved {len(chats)} chat entries for user {current_user.id}")
        return chats
    except Exception as e:
        logger.error(f"Error fetching chat history for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching chat history: {str(e)}")

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
    logger.info(f"Fetching chat history for session {session_id}")
    try:
        db_session = db.query(DBSession).filter(DBSession.id == session_id).first()
        if not db_session:
            logger.warning(f"Session {session_id} not found")
            raise HTTPException(status_code=404, detail="Session not found")
        if db_session.user_id != current_user.id and not db_session.is_public: # Allow access if session is public
             raise HTTPException(status_code=403, detail="Not authorized to view this session's history")
        
        chats = db.query(Chat).filter(
            Chat.session_id == session_id
        ).order_by(Chat.created_at).all() # Order by creation time for chronological history
        logger.info(f"Retrieved {len(chats)} chat entries for session {session_id}")
        return chats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching session chat history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching session chat history: {str(e)}")
