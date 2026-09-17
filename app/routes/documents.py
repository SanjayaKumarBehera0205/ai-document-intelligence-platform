import hashlib
import math
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Document, DocumentType, ProcessingStatus, User
from app.schemas import DashboardRead, DocumentDetail, DocumentPage, DocumentRead
from app.services import add_audit, process_document
from app.tasks import process_document_task

router = APIRouter(tags=["Documents"])
ALLOWED_TYPES = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg", "text/plain": ".txt", "text/markdown": ".md"}


def owned_document(document_id: int, user_id: int, db: Session) -> Document:
    document = db.scalar(select(Document).where(Document.id == document_id, Document.owner_id == user_id))
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.post("/documents", response_model=DocumentRead, status_code=202)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Supported formats: PDF, PNG, JPEG, TXT, and Markdown")
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Maximum upload size is {settings.max_upload_mb} MB")
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ALLOWED_TYPES[mime_type]}"
    (settings.storage_dir / stored_name).write_bytes(content)
    document = Document(owner_id=user.id, original_name=Path(file.filename or "document").name, stored_name=stored_name, mime_type=mime_type, size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
    db.add(document)
    db.flush()
    add_audit(user.id, "document.uploaded", "document", str(document.id), {"name": document.original_name}, db)
    db.commit()
    db.refresh(document)
    if settings.celery_enabled:
        process_document_task.delay(document.id)
    else:
        process_document(document.id)
        db.refresh(document)
    return document


@router.get("/documents", response_model=DocumentPage)
def list_documents(
    status: ProcessingStatus | None = None,
    document_type: DocumentType | None = Query(default=None, alias="type"),
    search: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filters = [Document.owner_id == user.id]
    if status:
        filters.append(Document.status == status)
    if document_type:
        filters.append(Document.document_type == document_type)
    if search:
        term = f"%{search.strip()}%"
        filters.append(or_(Document.original_name.ilike(term), Document.extracted_text.ilike(term)))
    total = db.scalar(select(func.count()).select_from(Document).where(*filters)) or 0
    items = list(db.scalars(select(Document).where(*filters).order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)))
    return DocumentPage(items=items, total=total, page=page, page_size=page_size, pages=math.ceil(total / page_size) if total else 0)


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return owned_document(document_id, user.id, db)


@router.post("/documents/{document_id}/reprocess", response_model=DocumentRead, status_code=202)
def reprocess(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document = owned_document(document_id, user.id, db)
    document.status = ProcessingStatus.PENDING
    document.error_message = None
    db.commit()
    if settings.celery_enabled:
        process_document_task.delay(document.id)
    else:
        process_document(document.id)
        db.refresh(document)
    return document


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document = owned_document(document_id, user.id, db)
    path = settings.storage_dir / document.stored_name
    path.unlink(missing_ok=True)
    add_audit(user.id, "document.deleted", "document", str(document.id), {"name": document.original_name}, db)
    db.delete(document)
    db.commit()
    return Response(status_code=204)


@router.get("/dashboard", response_model=DashboardRead)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    base = Document.owner_id == user.id
    count = lambda *extra: db.scalar(select(func.count()).select_from(Document).where(base, *extra)) or 0
    type_rows = db.execute(select(Document.document_type, func.count()).where(base, Document.document_type.is_not(None)).group_by(Document.document_type)).all()
    return DashboardRead(total_documents=count(), completed=count(Document.status == ProcessingStatus.COMPLETED), processing=count(Document.status.in_([ProcessingStatus.PENDING, ProcessingStatus.PROCESSING])), failed=count(Document.status == ProcessingStatus.FAILED), by_type={row[0].value: row[1] for row in type_rows})
