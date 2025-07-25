from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from .chat import Chat

class SessionBase(BaseModel):
    name: Optional[str] = "Untitled Session"
    is_public: Optional[bool] = False

class SessionCreate(SessionBase):
    pass

class SessionUpdate(SessionBase):
    pass

# New schema for session rename operations
class SessionRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="New session name")

# New schema for bulk session delete operations
class BulkDeleteSessionsRequest(BaseModel):
    session_ids: List[str] = Field(..., min_items=1, max_items=50, description="List of session IDs to delete")

class BulkDeleteSessionsResponse(BaseModel):
    deleted_count: int = Field(..., description="Number of sessions successfully deleted")
    failed_ids: List[str] = Field(default=[], description="Session IDs that failed to delete")
    errors: List[str] = Field(default=[], description="Error messages for failed deletions")

class Session(SessionBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    chats: List[Chat] = [] #for chat history not going with the session 

    class Config:
        from_attributes = True

# New models for search functionality
class SessionSearchChat(BaseModel):
    """Chat model for search results with match information"""
    id: str
    prompt: str
    response: Optional[str] = None
    created_at: datetime
    match_type: Literal["prompt", "response", "both"] = Field(
        description="Where the search term was found"
    )
    
    class Config:
        from_attributes = True

class SessionSearchSession(BaseModel):
    """Session model for search results"""
    id: str
    name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class SessionSearchResult(BaseModel):
    """Individual search result containing session and matching chats"""
    session: SessionSearchSession
    matching_chats: List[SessionSearchChat]
    total_matches_in_session: int = Field(
        description="Total number of matching chats in this session"
    )

class SessionSearchResponse(BaseModel):
    """Complete search response with pagination"""
    results: List[SessionSearchResult]
    total_results: int = Field(
        description="Total number of sessions with matches"
    )
    total_chat_matches: int = Field(
        description="Total number of individual chat matches across all sessions"
    )
    has_more: bool = Field(
        description="Whether there are more results available"
    )
    query: str = Field(
        description="The search query that was executed"
    )
    search_in: Literal["prompts", "responses", "both"] = Field(
        description="What was searched in"
    ) 