from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import json
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
    Generate a concise name for a chat conversation using OpenAI API.
    This is the exact same implementation as retello/ui/app.py
    """
    # Use OpenAI API (same as retello/ui/app.py)
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    if not isinstance(chat_history, list):
        raise ValueError("chat_history must be a list")
    
    filtered_messages = []
    for message in chat_history:
        if not isinstance(message, dict):
            continue
        if message.get('role') in ['user', 'assistant'] and message.get('content'):
            filtered_messages.append({
                message['role']: message['content']
            })

    if not filtered_messages:
        return "Empty Chat History"

    function_schema = {
        "name": "chat_name",
        "description": "Generate a concise, neutral summary name for the chat conversation that helps users identify and refer back to this chat",
        "parameters": {
            "type": "object",
            "properties": {
                "chat_name": {
                    "type": "string",
                    "description": "A concise summary name (typically 4-6 words) that captures the main topic or theme of the conversation"
                }
            },
            "required": ["chat_name"]
        }
    }

    system_prompt = [{
        "role": "system",
        "content": "You are tasked with creating a concise, neutral name for a chat conversation. The name should be 4-6 words that capture the main topic or theme, helping users easily identify and reference this chat later. Focus on the primary subject matter discussed."
    },
    {
        "role": "user",
        "content": f"{filtered_messages}"
    }]
    
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=system_prompt,
            functions=[function_schema],
            function_call={"name": "chat_name"}
        )

        message = response.choices[0].message
        
        if hasattr(message, 'function_call') and message.function_call:
            function_call = message.function_call
            if function_call.name == "chat_name":
                try:
                    function_args = json.loads(function_call.arguments)
                    chat_name = function_args.get('chat_name', '').strip()
                    if chat_name:
                        return chat_name
                except json.JSONDecodeError:
                    pass
        if hasattr(message, 'content') and message.content:
            return message.content.strip()
        
        return "Untitled Chat"
        
    except Exception as e:
        raise Exception(f"OpenAI API call failed: {str(e)}")

@router.post("/generate", response_model=ChatNameResponse)
async def generate_chat_name_endpoint(
    request: ChatNameRequest,
    current_user: User = Depends(get_current_user)
) -> ChatNameResponse:
    """
    Generate a concise name for a chat conversation based on chat history.
    Now uses the same OpenAI implementation as retello/ui/app.py
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
    Now uses the same OpenAI implementation as retello/ui/app.py
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