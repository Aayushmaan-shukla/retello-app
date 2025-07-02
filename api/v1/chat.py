from typing import Any, List, Union
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
import google.generativeai as genai
from pydantic import BaseModel, field_validator, model_validator
import re

from app.core.config import settings
from app.db.base import get_db
from app.models.chat import Chat
from app.models.session import Session as DBSession # Renamed to avoid conflict with sqlalchemy.orm.Session
from app.schemas.chat import ChatCreate, Chat as ChatSchema
from app.api.v1.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("chat")

# Pydantic models for why-this-phone endpoint
class ChatMessage(BaseModel):
    role: str
    content: str

class PhoneData(BaseModel):
    name: str
    brand: str = None
    price: Union[float, str, None] = None
    camera_mp: Union[int, str, None] = None
    battery_mah: Union[int, str, None] = None
    storage_gb: Union[int, str, None] = None
    ram_gb: Union[int, str, None] = None
    screen_size: Union[float, str, None] = None
    processor: str = None
    
    # Allow additional fields
    class Config:
        extra = "allow"
    
    @field_validator('price', mode='before')
    @classmethod
    def validate_price(cls, v):
        """Convert price from various formats to float"""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            # Remove currency symbols, commas, and extract numbers
            # Examples: "$999", "999.99", "₹50,000", "999 USD"
            cleaned = re.sub(r'[^\d.]', '', v)
            if cleaned:
                try:
                    return float(cleaned)
                except ValueError:
                    pass
        return None
    
    @field_validator('camera_mp', mode='before')
    @classmethod
    def validate_camera_mp(cls, v):
        """Convert camera MP from various formats to int"""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, (float, str)):
            # Extract numbers from strings like "48MP", "48 megapixels", "48.0"
            match = re.search(r'(\d+)', str(v))
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        return None
    
    @field_validator('battery_mah', mode='before')
    @classmethod
    def validate_battery_mah(cls, v):
        """Convert battery capacity from various formats to int"""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, (float, str)):
            # Extract numbers from strings like "3274mAh", "3274 mAh", "3274"
            match = re.search(r'(\d+)', str(v))
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        return None
    
    @field_validator('storage_gb', mode='before')
    @classmethod
    def validate_storage_gb(cls, v):
        """Convert storage from various formats to int (convert to GB)"""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, (float, str)):
            # Handle various formats: "128GB", "1TB", "256 GB", "512"
            s = str(v).upper()
            # Extract number and check for TB
            match = re.search(r'(\d+)', s)
            if match:
                try:
                    number = int(match.group(1))
                    if 'TB' in s:
                        return number * 1024  # Convert TB to GB
                    return number
                except ValueError:
                    pass
        return None
    
    @field_validator('ram_gb', mode='before')
    @classmethod
    def validate_ram_gb(cls, v):
        """Convert RAM from various formats to int"""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, (float, str)):
            # Extract numbers from strings like "8GB", "8 GB RAM", "8"
            match = re.search(r'(\d+)', str(v))
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        return None
    
    @field_validator('screen_size', mode='before')
    @classmethod
    def validate_screen_size(cls, v):
        """Convert screen size from various formats to float"""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            # Extract numbers from strings like "6.1 inches", "6.1\"", "6.1 in"
            match = re.search(r'(\d+\.?\d*)', v)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    pass
        return None
    
    @model_validator(mode='before')
    @classmethod
    def handle_field_variations(cls, data):
        """Handle different field name variations and common aliases"""
        if isinstance(data, dict):
            # Create a copy to avoid modifying the original
            processed_data = data.copy()
            
            # Handle battery field variations
            if 'battery_capacity' in processed_data and 'battery_mah' not in processed_data:
                processed_data['battery_mah'] = processed_data.get('battery_capacity')
            
            # Handle camera field variations  
            if 'main_camera_mp' in processed_data and 'camera_mp' not in processed_data:
                processed_data['camera_mp'] = processed_data.get('main_camera_mp')
            
            # Handle screen size variations
            if 'display_size' in processed_data and 'screen_size' not in processed_data:
                processed_data['screen_size'] = processed_data.get('display_size')
            
            # Handle storage variations
            if 'storage_size' in processed_data and 'storage_gb' not in processed_data:
                processed_data['storage_gb'] = processed_data.get('storage_size')
            
            # Handle RAM variations
            if 'ram_size' in processed_data and 'ram_gb' not in processed_data:
                processed_data['ram_gb'] = processed_data.get('ram_size')
            
            return processed_data
        return data

class WhyThisPhoneRequest(BaseModel):
    chat_history: List[ChatMessage]
    phone: PhoneData

class WhyThisPhoneResponse(BaseModel):
    why_this_phone: str

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
                                if 'why_this_phone' in metadata_content:
                                    chat.why_this_phone = metadata_content['why_this_phone']
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
    logger.info(f"Stream wrapper called for chat {chat_id}")
    logger.info(f"Payload keys: {list(json_payload.keys())}")
    logger.info(f"Conversation length in payload: {len(json_payload.get('conversation', []))}")
    if 'current_params' in json_payload:
        logger.info(f"Current params present: {bool(json_payload['current_params'])}")
    
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
            logger.error(f"HTTPStatusError: {e_http_status.request.url} - Status {e_http_status.response.status_code}")
            await handle_streaming_error(db, chat_id, e_http_status)
            error_content = f'External service error: {e_http_status.response.status_code}'
            try: # Try to get more details from response if JSON
                error_details = e_http_status.response.json()
                error_content += f" - {json.dumps(error_details)}"
            except json.JSONDecodeError:
                error_content += f" - {e_http_status.response.text[:200]}" # First 200 chars of text response

            yield f"data: {json.dumps({'type': 'error', 'content': error_content})}\n\n"
        except httpx.RequestError as e_request: # Covers network errors, DNS failures, timeouts before response, etc.
            logger.error(f"RequestError: {e_request.request.url} - {e_request}")
            await handle_streaming_error(db, chat_id, e_request)
            yield f"data: {json.dumps({'type': 'error', 'content': f'Error connecting to external service: {str(e_request)}'})}\n\n"
        except Exception as e_unexpected:
            logger.error(f"Unexpected error: {e_unexpected}")
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

        # Build conversation with previous history
        base_system_content = "You are an intelligent phone recommendation assistant by a company called \"Retello\"\nAvailable features and their descriptions:\n{\n  \"battery_capacity\": \"Battery size in mAh\",\n  \"main_camera\": \"Main camera resolution in MP\",\n  \"front_camera\": \"Front camera resolution in MP\",\n  \"screen_size\": \"Screen size in inches\",\n  \"charging_speed\": \"Charging speed in watts\",\n  \"os\": \"Android version\",\n  \"camera_count\": \"Number of cameras\",\n  \"sensors\": \"Available sensors\",\n  \"display_type\": \"Display technology\",\n  \"network\": \"Network connectivity\",\n  \"chipset\": \"processor/chipset name\",\n  \"preferred_brands\": \"names of the brands preferred by a user\",\n  \"price_range\": \"price a user is willing to pay\"\n}\n\nMap user requirements to these specific features if possible. Consider both explicit and implicit needs."
        
        # Add conversation summary if there are previous chats
        if formatted_chats and len(formatted_chats) > 0:
            # Create a summary of recent interactions
            recent_user_queries = []
            recent_recommendations = []
            
            # Extract last few user queries and phone recommendations
            for i in range(0, min(len(formatted_chats), 6), 2):  # Last 3 interactions
                if i < len(formatted_chats):
                    user_msg = formatted_chats[i].get('content', '')
                    if len(user_msg) > 10:
                        recent_user_queries.append(user_msg[:100])
                
                if i + 1 < len(formatted_chats):
                    assistant_msg = formatted_chats[i + 1].get('content', '')
                    # Extract phone names from assistant response
                    if 'phone' in assistant_msg.lower() and len(assistant_msg) > 20:
                        recent_recommendations.append(assistant_msg[:150])
            
            if recent_user_queries or recent_recommendations:
                conversation_summary = "\n\nCONVERSATION CONTEXT:"
                if recent_user_queries:
                    conversation_summary += f"\nRecent user requests: {'; '.join(recent_user_queries[-2:])}"
                if recent_recommendations:
                    conversation_summary += f"\nRecent recommendations provided: {'; '.join(recent_recommendations[-2:])}"
                conversation_summary += "\nUse this context to maintain continuity in your responses."
                
                base_system_content += conversation_summary
                logger.info(f"Added conversation summary to system prompt (queries: {len(recent_user_queries)}, recs: {len(recent_recommendations)})")
        
        # DON'T send system prompt to microservice since it adds its own
        # Instead, send just the conversation history without system prompt
        conversation_for_microservice = []
        
        # Add previous conversation history if available
        if formatted_chats:
            conversation_for_microservice.extend(formatted_chats)
            logger.info(f"Added {len(formatted_chats)} previous messages to conversation for microservice")
        
        # Add current user input
        conversation_for_microservice.append({"role": "user", "content": chat_in.prompt})

        prompt_payload = {
            "user_input": chat_in.prompt,
            "conversation": conversation_for_microservice  # No system prompt
        }
        
        # Try alternative approaches to send conversation history
        # Approach 1: Embed conversation in user_input itself
        if formatted_chats and len(formatted_chats) > 0:
            # Create conversation context as part of user input
            context_summary = "\n\n[CONVERSATION CONTEXT]:\n"
            for i in range(max(0, len(formatted_chats)-4), len(formatted_chats), 2):
                if i < len(formatted_chats):
                    user_msg = formatted_chats[i].get('content', '')[:100]
                    context_summary += f"Previous User: {user_msg}\n"
                if i + 1 < len(formatted_chats):
                    assistant_msg = formatted_chats[i + 1].get('content', '')[:100]
                    context_summary += f"Previous Assistant: {assistant_msg}\n"
            
            context_summary += f"\n[CURRENT QUESTION]: {chat_in.prompt}"
            
            # Try embedding context in user_input
            prompt_payload["user_input_with_context"] = context_summary
            prompt_payload["conversation_history"] = formatted_chats  # Alternative parameter name
            prompt_payload["messages"] = conversation_for_microservice  # Try 'messages' instead of 'conversation'
            
            logger.info(f"Added conversation context to user_input and alternative parameters")
        
        # Include current_params from last chat if available
        if recent_db_session:
            last_chat = db.query(Chat).filter(Chat.session_id == session_id).order_by(Chat.created_at.desc()).first()
            if last_chat and last_chat.current_params:
                prompt_payload["current_params"] = last_chat.current_params
                logger.info(f"Including current_params from last chat in session {session_id}")

        chat_id = str(uuid.uuid4())
        logger.info(f"Creating new chat {chat_id} in session {session_id}")
        logger.info(f"Payload conversation length: {len(conversation_for_microservice)} (including system prompt)")
        logger.info(f"Sending payload to microservice: user_input='{chat_in.prompt}', conversation_length={len(conversation_for_microservice)}")
        
        # Debug: Log the conversation structure (last few messages)
        if len(conversation_for_microservice) > 3:
            logger.info("Last 3 conversation messages being sent:")
            for i, msg in enumerate(conversation_for_microservice[-3:]):
                logger.info(f"  [{i}] {msg['role']}: {msg['content'][:100]}...")
        else:
            logger.info("Full conversation being sent:")
            for i, msg in enumerate(conversation_for_microservice):
                logger.info(f"  [{i}] {msg['role']}: {msg['content'][:100]}...")
        
        db_chat = Chat(
            id=chat_id,
            user_id=current_user.id,
            session_id=session_id,
            prompt=chat_in.prompt,
            response="",
            phones=[],
            current_params={},
            button_text="See more", # Default value
            why_this_phone=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(db_chat)
        db.commit() # Commit chat entry so stream_response can find it

        logger.info(f"Starting streaming response for chat {chat_id} with {len(conversation_for_microservice)-2} previous messages")
        
        # Detailed logging of what's being sent to LLM layer
        logger.info("=== DETAILED PAYLOAD TO LLM LAYER ===")
        logger.info(f"Payload keys: {list(prompt_payload.keys())}")
        
        # Log conversation structure
        if 'conversation' in prompt_payload:
            logger.info(f"CONVERSATION array length: {len(prompt_payload['conversation'])}")
            for i, msg in enumerate(prompt_payload['conversation']):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')[:150] + "..." if len(msg.get('content', '')) > 150 else msg.get('content', '')
                logger.info(f"  conversation[{i}] - {role}: {content}")
        
        # Log formatted chats
        if formatted_chats:
            logger.info(f"FORMATTED_CHATS length: {len(formatted_chats)}")
            for i, msg in enumerate(formatted_chats):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')[:100] + "..." if len(msg.get('content', '')) > 100 else msg.get('content', '')
                logger.info(f"  formatted_chats[{i}] - {role}: {content}")
        
        # Log alternative parameters
        if 'user_input_with_context' in prompt_payload:
            context_content = prompt_payload['user_input_with_context'][:200] + "..." if len(prompt_payload['user_input_with_context']) > 200 else prompt_payload['user_input_with_context']
            logger.info(f"USER_INPUT_WITH_CONTEXT: {context_content}")
        
        if 'conversation_history' in prompt_payload:
            logger.info(f"CONVERSATION_HISTORY length: {len(prompt_payload['conversation_history'])}")
        
        if 'messages' in prompt_payload:
            logger.info(f"MESSAGES array length: {len(prompt_payload['messages'])}")
        
        if 'current_params' in prompt_payload:
            logger.info(f"CURRENT_PARAMS present: {bool(prompt_payload['current_params'])}")
            if prompt_payload['current_params']:
                params_str = str(prompt_payload['current_params'])[:200] + "..." if len(str(prompt_payload['current_params'])) > 200 else str(prompt_payload['current_params'])
                logger.info(f"CURRENT_PARAMS content: {params_str}")
        
        logger.info("=== END PAYLOAD TO LLM LAYER ===")
        
        return StreamingResponse(
            stream_response_wrapper(settings.MICRO_URL, prompt_payload, db, chat_id),
            media_type="text/event-stream"
        )

    except Exception as e:
        logger.error(f"Error creating chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating chat: {str(e)}")

@router.post("/why-this-phone", response_model=WhyThisPhoneResponse)
async def why_this_phone(
    request: WhyThisPhoneRequest,
    current_user: User = Depends(get_current_user)
) -> WhyThisPhoneResponse:
    """
    Generate explanation for why a specific phone matches user's needs
    based on their chat history and phone specifications.
    
    Calls external microservice following the same pattern as /ask endpoint.
    """
    try:
        # Validate inputs
        if not request.chat_history:
            raise HTTPException(status_code=400, detail="Chat history cannot be empty")
        
        if not request.phone.name:
            raise HTTPException(status_code=400, detail="Phone name is required")
        
        # Convert chat history to the format expected by microservice
        conversation = []
        for message in request.chat_history:
            conversation.append({
                "role": message.role,
                "content": message.content
            })
        
        # Prepare payload for external microservice
        payload = {
            "chat_history": conversation,
            "phone": request.phone.dict(),
            "request_type": "why_this_phone",
            "user_id": current_user.id
        }
        
        logger.info(f"Calling why-this-phone microservice for phone: {request.phone.name}, user: {current_user.id}")
        
        # Call external microservice (same pattern as /ask endpoint)
        microservice_url = settings.WHY_THIS_PHONE_URL
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    microservice_url,
                    json=payload,
                    timeout=30.0  # Non-streaming, so shorter timeout
                )
                response.raise_for_status()
                
                result = response.json()
                
                # Extract the explanation from microservice response
                explanation = result.get("why_this_phone", "")
                
                if not explanation:
                    raise HTTPException(status_code=500, detail="Empty response from microservice")
                
                logger.info(f"Successfully generated why-this-phone explanation for {request.phone.name}")
                return WhyThisPhoneResponse(why_this_phone=explanation)
                
            except httpx.HTTPStatusError as e:
                logger.error(f"Microservice HTTP error: {e.response.status_code} - {e.response.text}")
                raise HTTPException(
                    status_code=502, 
                    detail=f"External service error: {e.response.status_code}"
                )
            except httpx.RequestError as e:
                logger.error(f"Microservice request error: {str(e)}")
                raise HTTPException(
                    status_code=503, 
                    detail="Unable to connect to phone explanation service"
                )
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response from microservice: {str(e)}")
                raise HTTPException(
                    status_code=502, 
                    detail="Invalid response format from external service"
                )
                
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in why-this-phone endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

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

    # Get previous chats from this session (excluding any incomplete ones)
    prev_chats = db.query(Chat).filter(
        Chat.session_id == session_id,
        Chat.response.isnot(None),
        Chat.response != "",
        Chat.response != "I am sorry, I don't have a response for that."
    ).order_by(Chat.created_at).all()
    
    logger.info(f"Found {len(prev_chats)} previous chats in session {session_id}")
    
    formatted_chats = []
    for chat_item in prev_chats:
        # Only include chats with meaningful responses
        response_content = chat_item.response.strip() if chat_item.response else ""
        if response_content and len(response_content) > 10:  # Ensure meaningful content
            formatted_chats.extend([
                {"role": "user", "content": chat_item.prompt},
                {"role": "assistant", "content": response_content}
            ])
        else:
            logger.warning(f"Skipping chat with insufficient response: {chat_item.id}")
    
    logger.info(f"Formatted {len(formatted_chats)} conversation messages from {len(prev_chats)} previous chats")

    # Build conversation with previous history
    base_system_content = "You are an intelligent phone recommendation assistant by a company called \"Retello\"\nAvailable features and their descriptions:\n{\n  \"battery_capacity\": \"Battery size in mAh\",\n  \"main_camera\": \"Main camera resolution in MP\",\n  \"front_camera\": \"Front camera resolution in MP\",\n  \"screen_size\": \"Screen size in inches\",\n  \"charging_speed\": \"Charging speed in watts\",\n  \"os\": \"Android version\",\n  \"camera_count\": \"Number of cameras\",\n  \"sensors\": \"Available sensors\",\n  \"display_type\": \"Display technology\",\n  \"network\": \"Network connectivity\",\n  \"chipset\": \"processor/chipset name\",\n  \"preferred_brands\": \"names of the brands preferred by a user\",\n  \"price_range\": \"price a user is willing to pay\"\n}\n\nMap user requirements to these specific features if possible. Consider both explicit and implicit needs."
    
    # Add conversation summary if there are previous chats
    if formatted_chats and len(formatted_chats) > 0:
        # Create a summary of recent interactions
        recent_user_queries = []
        recent_recommendations = []
        
        # Extract last few user queries and phone recommendations
        for i in range(0, min(len(formatted_chats), 6), 2):  # Last 3 interactions
            if i < len(formatted_chats):
                user_msg = formatted_chats[i].get('content', '')
                if len(user_msg) > 10:
                    recent_user_queries.append(user_msg[:100])
            
            if i + 1 < len(formatted_chats):
                assistant_msg = formatted_chats[i + 1].get('content', '')
                # Extract phone names from assistant response
                if 'phone' in assistant_msg.lower() and len(assistant_msg) > 20:
                    recent_recommendations.append(assistant_msg[:150])
        
        if recent_user_queries or recent_recommendations:
            conversation_summary = "\n\nCONVERSATION CONTEXT:"
            if recent_user_queries:
                conversation_summary += f"\nRecent user requests: {'; '.join(recent_user_queries[-2:])}"
            if recent_recommendations:
                conversation_summary += f"\nRecent recommendations provided: {'; '.join(recent_recommendations[-2:])}"
            conversation_summary += "\nUse this context to maintain continuity in your responses."
            
            base_system_content += conversation_summary
            logger.info(f"Added conversation summary to system prompt (queries: {len(recent_user_queries)}, recs: {len(recent_recommendations)})")
    
    # DON'T send system prompt to microservice since it adds its own
    # Instead, send just the conversation history without system prompt
    conversation_for_microservice = []
    
    # Add previous conversation history if available
    if formatted_chats:
        conversation_for_microservice.extend(formatted_chats)
        logger.info(f"Added {len(formatted_chats)} previous messages to conversation for microservice")
    
    # Add current user input
    conversation_for_microservice.append({"role": "user", "content": chat_in.prompt})

    prompt_payload = {
        "user_input": chat_in.prompt,
        "conversation": conversation_for_microservice  # No system prompt
    }
    
    # Try alternative approaches to send conversation history
    # Approach 1: Embed conversation in user_input itself
    if formatted_chats and len(formatted_chats) > 0:
        # Create conversation context as part of user input
        context_summary = "\n\n[CONVERSATION CONTEXT]:\n"
        for i in range(max(0, len(formatted_chats)-4), len(formatted_chats), 2):
            if i < len(formatted_chats):
                user_msg = formatted_chats[i].get('content', '')[:100]
                context_summary += f"Previous User: {user_msg}\n"
            if i + 1 < len(formatted_chats):
                assistant_msg = formatted_chats[i + 1].get('content', '')[:100]
                context_summary += f"Previous Assistant: {assistant_msg}\n"
        
        context_summary += f"\n[CURRENT QUESTION]: {chat_in.prompt}"
        
        # Try embedding context in user_input
        prompt_payload["user_input_with_context"] = context_summary
        prompt_payload["conversation_history"] = formatted_chats  # Alternative parameter name
        prompt_payload["messages"] = conversation_for_microservice  # Try 'messages' instead of 'conversation'
        
        logger.info(f"Added conversation context to user_input and alternative parameters")
    
    # Include current_params from last chat if available
    if prev_chats:
        last_chat = prev_chats[-1]
        if last_chat.current_params:
            prompt_payload["current_params"] = last_chat.current_params
            logger.info(f"Including current_params from last chat: {last_chat.current_params}")
        else:
            logger.info("No current_params found in last chat")
    else:
        logger.info("No previous chats found for current_params")

    chat_id = str(uuid.uuid4())
    logger.info(f"Creating new chat {chat_id} in session {session_id}")
    logger.info(f"Payload conversation length: {len(conversation_for_microservice)} (including system prompt)")
    logger.info(f"Sending payload to microservice: user_input='{chat_in.prompt}', conversation_length={len(conversation_for_microservice)}")
    
    # Debug: Log the conversation structure (last few messages)
    if len(conversation_for_microservice) > 3:
        logger.info("Last 3 conversation messages being sent:")
        for i, msg in enumerate(conversation_for_microservice[-3:]):
            logger.info(f"  [{i}] {msg['role']}: {msg['content'][:100]}...")
    else:
        logger.info("Full conversation being sent:")
        for i, msg in enumerate(conversation_for_microservice):
            logger.info(f"  [{i}] {msg['role']}: {msg['content'][:100]}...")
    
    db_chat = Chat(
        id=chat_id,
        user_id=current_user.id,
        session_id=session_id,
        prompt=chat_in.prompt,
        response="",
        phones=[],
        current_params={},
        button_text="See more", # Default value
        why_this_phone=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(db_chat)
    db.commit() # Commit chat entry and session update

    # Detailed logging of what's being sent to LLM layer
    logger.info("=== DETAILED PAYLOAD TO LLM LAYER (CONTINUE_CHAT) ===")
    logger.info(f"Payload keys: {list(prompt_payload.keys())}")
    
    # Log conversation structure
    if 'conversation' in prompt_payload:
        logger.info(f"CONVERSATION array length: {len(prompt_payload['conversation'])}")
        for i, msg in enumerate(prompt_payload['conversation']):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')[:150] + "..." if len(msg.get('content', '')) > 150 else msg.get('content', '')
            logger.info(f"  conversation[{i}] - {role}: {content}")
    
    # Log formatted chats
    if formatted_chats:
        logger.info(f"FORMATTED_CHATS length: {len(formatted_chats)}")
        for i, msg in enumerate(formatted_chats):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')[:100] + "..." if len(msg.get('content', '')) > 100 else msg.get('content', '')
            logger.info(f"  formatted_chats[{i}] - {role}: {content}")
    
    # Log alternative parameters
    if 'user_input_with_context' in prompt_payload:
        context_content = prompt_payload['user_input_with_context'][:200] + "..." if len(prompt_payload['user_input_with_context']) > 200 else prompt_payload['user_input_with_context']
        logger.info(f"USER_INPUT_WITH_CONTEXT: {context_content}")
    
    if 'conversation_history' in prompt_payload:
        logger.info(f"CONVERSATION_HISTORY length: {len(prompt_payload['conversation_history'])}")
    
    if 'messages' in prompt_payload:
        logger.info(f"MESSAGES array length: {len(prompt_payload['messages'])}")
    
    if 'current_params' in prompt_payload:
        logger.info(f"CURRENT_PARAMS present: {bool(prompt_payload['current_params'])}")
        if prompt_payload['current_params']:
            params_str = str(prompt_payload['current_params'])[:200] + "..." if len(str(prompt_payload['current_params'])) > 200 else str(prompt_payload['current_params'])
            logger.info(f"CURRENT_PARAMS content: {params_str}")
    
    logger.info("=== END PAYLOAD TO LLM LAYER (CONTINUE_CHAT) ===")

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


