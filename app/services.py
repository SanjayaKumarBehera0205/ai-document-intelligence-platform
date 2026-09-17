from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.models import AuditLog, Document, ProcessingStatus
from app.processor import process_file


def add_audit(user_id: int, action: str, resource_type: str, resource_id: str | None = None, details: dict | None = None, db=None) -> None:
    owns_session = db is None
    session = db or SessionLocal()
    session.add(AuditLog(user_id=user_id, action=action, resource_type=resource_type, resource_id=resource_id, details=details))
    if owns_session:
        session.commit()
        session.close()


def process_document(document_id: int) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None:
            return
        document.status = ProcessingStatus.PROCESSING
        db.commit()
        try:
            path = settings.storage_dir / document.stored_name
            text, doc_type, confidence, data = process_file(path, document.mime_type)
            document.extracted_text = text
            document.document_type = doc_type
            document.confidence = confidence
            document.extracted_data = data
            document.status = ProcessingStatus.COMPLETED
            document.processed_at = datetime.now(timezone.utc)
            add_audit(document.owner_id, "document.processed", "document", str(document.id), {"type": doc_type.value}, db)
        except Exception as exc:
            document.status = ProcessingStatus.FAILED
            document.error_message = str(exc)[:1000]
            document.processed_at = datetime.now(timezone.utc)
            add_audit(document.owner_id, "document.failed", "document", str(document.id), {"error": str(exc)[:200]}, db)
        db.commit()
