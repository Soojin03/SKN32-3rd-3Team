from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    display_name: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    display_name: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class DocumentCreate(BaseModel):
    title: str
    content: Optional[str] = ""
    summary: Optional[str] = None
    source_type: Optional[Literal["manual", "meeting_transcript", "meeting_summary"]] = "manual"
    parent_id: Optional[int] = None

class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    parent_id: Optional[int] = None

class DocumentResponse(BaseModel):
    id: int
    owner_id: int
    title: str
    content: str
    summary: Optional[str]
    source_type: str
    parent_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class DocumentTreeNode(DocumentResponse):
    children: List["DocumentTreeNode"] = []

DocumentTreeNode.model_rebuild()

class GeminiRequest(BaseModel):
    prompt: str