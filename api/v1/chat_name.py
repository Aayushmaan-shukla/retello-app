from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import json
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

def generate_chat_name(chat_history: List[Dict[str, str]]) -> str:
    """
    Generate a concise name for a chat conversation using Google Gemini API.
    """
    # Configure the Gemini API
    genai.configure(api_key=settings.GEMINI_API_KEY)
    
    if not isinstance(chat_history, list):
        raise ValueError("chat_history must be a list")
    
    filtered_messages = []
    for message in chat_history:
        if not isinstance(message, dict):
            continue
        if message.get('role') in ['user', 'assistant'] and message.get('content'):
            role = "user" if message['role'] == 'user' else "assistant"
            filtered_messages.append(f"{role}: {message['content']}")

    if not filtered_messages:
        return "Empty Chat History"

    # Create the conversation context
    conversation_text = "\n".join(filtered_messages)
    
    # Create the prompt for Gemini
    prompt = f"""
You are tasked with creating a concise, neutral name for a chat conversation. 
The name should be 4-6 words that capture the main topic or theme, helping users easily identify and reference this chat later. 
Focus on the primary subject matter discussed.

Conversation:
{conversation_text}

Generate a concise summary name (typically 4-6 words) that captures the main topic or theme of the conversation.
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
        
        return "Untitled Chat"
        
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