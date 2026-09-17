from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import DocumentType, ProcessingStatus, UserRole


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    role: UserRole
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    original_name: str
    mime_type: str
    size_bytes: int
    status: ProcessingStatus
    document_type: DocumentType | None
    confidence: float | None
    extracted_data: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    processed_at: datetime | None


class DocumentDetail(DocumentRead):
    extracted_text: str | None


class DocumentPage(BaseModel):
    items: list[DocumentRead]
    total: int
    page: int
    page_size: int
    pages: int


class DashboardRead(BaseModel):
    total_documents: int
    completed: int
    processing: int
    failed: int
    by_type: dict[str, int]
