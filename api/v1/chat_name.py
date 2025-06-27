from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import json
import re
import google.generativeai as genai
from openai import OpenAI
from app.core.config import settings
from app.db.base import get_db
from app.models.chat import Chat
from app.models.session import Session as DBSession
from app.api.v1.auth import get_current_user
from app.models.user import User
from pydantic import BaseModel

router = APIRouter(prefix="/chat-name", tags=["chat-name"])

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatNameRequest(BaseModel):
    chat_history: List[ChatMessage]

class ChatNameResponse(BaseModel):
    summary: str

class SessionNameRequest(BaseModel):
    session_id: str

class ChatNameEligibilityRequest(BaseModel):
    chat_history: List[ChatMessage]

class ChatNameEligibilityResponse(BaseModel):
    should_generate: bool
    reason: str
    meaningful_message_count: int

def is_meaningful_message(content: str) -> bool:
    """
    Determine if a message contains meaningful content worth considering for chat naming.
    Returns False for greetings, single words, or generic responses.
    """
    if not content or not isinstance(content, str):
        return False
    
    # Clean and normalize the content
    content = content.strip().lower()
    
    # Skip if too short (less than 10 characters or single word)
    if len(content) < 10 or len(content.split()) <= 2:
        return False
    
    # Special check for extended greetings that are still generic
    if len(content.split()) <= 6 and any(greeting in content for greeting in ['hi', 'hello', 'hey', 'how are you']):
        return False
    
    # Common greetings and generic phrases to ignore
    generic_patterns = [
        r'^(hi|hello|hey|sup|yo)(\s+there)?[\s\.,!]*$',
        r'^(how\s+are\s+you|how\s+do\s+you\s+do)[\s\.,!]*$',
        r'^(good\s+morning|good\s+afternoon|good\s+evening)[\s\.,!]*$',
        r'^(thanks?|thank\s+you|ty)[\s\.,!]*$',
        r'^(bye|goodbye|see\s+you|ttyl)[\s\.,!]*$',
        r'^(ok|okay|alright|sure|yes|no|yep|nope)[\s\.,!]*$',
        r'^(what\'?s\s+up|whats\s+up|wassup)[\s\.,!]*$',
        r'^(nice|cool|awesome|great)[\s\.,!]*$',
        r'^(i\s+see|got\s+it|understood)[\s\.,!]*$',
    ]
    
    # Check against generic patterns
    for pattern in generic_patterns:
        if re.match(pattern, content):
            return False
    
    # Look for question words or meaningful content indicators
    meaningful_indicators = [
        'what', 'how', 'why', 'when', 'where', 'which', 'who',
        'can you', 'could you', 'would you', 'should i', 'can i',
        'tell me', 'explain', 'help me', 'show me', 'find',
        'recommend', 'suggest', 'compare', 'difference',
        'phone', 'mobile', 'smartphone', 'device', 'budget',
        'camera', 'battery', 'performance', 'gaming', 'price'
    ]
    
    # Check if content contains meaningful indicators
    return any(indicator in content for indicator in meaningful_indicators)

def extract_meaningful_messages(chat_history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Extract only meaningful messages from chat history for name generation.
    """
    meaningful_messages = []
    
    for message in chat_history:
        if not isinstance(message, dict):
            continue
            
        role = message.get('role')
        content = message.get('content', '')
        
        if role not in ['user', 'assistant'] or not content:
            continue
        
        # For user messages, check if they're meaningful
        if role == 'user':
            if is_meaningful_message(content):
                meaningful_messages.append(message)
        # For assistant messages, include if we have a meaningful user message
        elif role == 'assistant' and meaningful_messages:
            # Only include assistant response if it follows a meaningful user message
            meaningful_messages.append(message)
    
    return meaningful_messages

def should_generate_chat_name(chat_history: List[Dict[str, str]]) -> bool:
    """
    Determine if the chat history contains enough meaningful content to warrant name generation.
    """
    meaningful_messages = extract_meaningful_messages(chat_history)
    
    # Need at least one meaningful user message
    user_messages = [msg for msg in meaningful_messages if msg.get('role') == 'user']
    
    return len(user_messages) >= 1

def generate_chat_name(chat_history: List[Dict[str, str]]) -> str:
    """
    Generate a concise name for a chat conversation using Google Gemini API.
    Only generates names for conversations with meaningful content.
    """
    # Configure the Gemini API
    genai.configure(api_key=settings.GEMINI_API_KEY)
    
    if not isinstance(chat_history, list):
        raise ValueError("chat_history must be a list")
    
    # Check if we should generate a name for this conversation
    if not should_generate_chat_name(chat_history):
        return "General Chat"  # Default name for non-meaningful chats
    
    # Extract only meaningful messages
    meaningful_messages = extract_meaningful_messages(chat_history)
    
    if not meaningful_messages:
        return "General Chat"
    
    # Format messages for the AI
    filtered_messages = []
    for message in meaningful_messages:
        role = "user" if message['role'] == 'user' else "assistant"
        filtered_messages.append(f"{role}: {message['content']}")

    # Create the conversation context
    conversation_text = "\n".join(filtered_messages)
    
    # Create the prompt for Gemini
    prompt = f"""
You are tasked with creating a concise, neutral name for a chat conversation. 
The name should be 4-6 words that capture the main topic or theme, helping users easily identify and reference this chat later. 
Focus on the primary subject matter discussed.

This conversation contains meaningful queries (greetings and generic responses have been filtered out):

Conversation:
{conversation_text}

Generate a concise summary name (typically 4-6 words) that captures the main topic or theme of the conversation.
Focus on the actual question or need being discussed.
Respond with ONLY the chat name, no additional text or explanation.
"""
    
    try:
        # Initialize the model
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Generate the response
        response = model.generate_content(prompt)
        
        if response.text:
            chat_name = response.text.strip()
            # Remove any quotes or extra formatting
            chat_name = chat_name.strip('"\'')
            if chat_name:
                return chat_name
        
        return "General Chat"
        
    except Exception as e:
        raise Exception(f"Gemini API call failed: {str(e)}")

@router.post("/generate", response_model=ChatNameResponse)
async def generate_chat_name_endpoint(
    request: ChatNameRequest,
    current_user: User = Depends(get_current_user)
) -> ChatNameResponse:
    """
    Generate a concise name for a chat conversation based on chat history.
    """
    try:
        # Convert Pydantic models to dict format expected by generate_chat_name
        chat_history_dict = [
            {"role": msg.role, "content": msg.content} 
            for msg in request.chat_history
        ]
        
        summary = generate_chat_name(chat_history_dict)
        return ChatNameResponse(summary=summary)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/generate-for-session", response_model=ChatNameResponse)
async def generate_session_name(
    request: SessionNameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> ChatNameResponse:
    """
    Generate a name for a session based on all chats in that session.
    """
    try:
        # Get session and verify ownership
        session = db.query(DBSession).filter(
            DBSession.id == request.session_id,
            DBSession.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get all chats for the session
        chats = db.query(Chat).filter(Chat.session_id == request.session_id).all()
        
        if not chats:
            return ChatNameResponse(summary="Empty Session")
        
        # Build chat history from all chats in the session
        chat_history = []
        for chat in chats:
            if chat.prompt:
                chat_history.append({"role": "user", "content": chat.prompt})
            if chat.response:
                chat_history.append({"role": "assistant", "content": chat.response})
        
        if not chat_history:
            return ChatNameResponse(summary="Empty Session")
        
        summary = generate_chat_name(chat_history)
        return ChatNameResponse(summary=summary)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/check-eligibility", response_model=ChatNameEligibilityResponse)
async def check_chat_name_eligibility(
    request: ChatNameEligibilityRequest,
    current_user: User = Depends(get_current_user)
) -> ChatNameEligibilityResponse:
    """
    Check if a chat conversation has enough meaningful content to warrant name generation.
    This can be used by the frontend to decide when to call the name generation endpoint.
    """
    try:
        # Convert Pydantic models to dict format
        chat_history_dict = [
            {"role": msg.role, "content": msg.content} 
            for msg in request.chat_history
        ]
        
        # Check if we should generate a name
        should_generate = should_generate_chat_name(chat_history_dict)
        meaningful_messages = extract_meaningful_messages(chat_history_dict)
        meaningful_count = len([msg for msg in meaningful_messages if msg.get('role') == 'user'])
        
        if should_generate:
            reason = f"Found {meaningful_count} meaningful user message(s) - ready for name generation"
        else:
            if not meaningful_messages:
                reason = "No meaningful messages found - only greetings or generic responses detected"
            else:
                reason = "Insufficient meaningful content for name generation"
        
        return ChatNameEligibilityResponse(
            should_generate=should_generate,
            reason=reason,
            meaningful_message_count=meaningful_count
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}") 