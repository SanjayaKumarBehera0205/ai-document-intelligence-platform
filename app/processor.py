import re
from pathlib import Path

from PIL import Image
from pypdf import PdfReader
import pytesseract

from app.models import DocumentType

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s()-]{7,}\d)")
MONEY_RE = re.compile(r"(?:total|amount due|grand total)\s*[:₹$€£]?\s*([\d,]+(?:\.\d{1,2})?)", re.I)
INVOICE_RE = re.compile(
    r"invoice[ \t]*(?:number|no\.?|#)[ \t]*[:#-]?[ \t]*([A-Z0-9-]+)", re.I
)
DATE_RE = re.compile(r"\b(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
SKILLS = {"python", "django", "fastapi", "sql", "aws", "gcp", "docker", "machine learning", "nlp", "pandas"}


def extract_text(path: Path, mime_type: str) -> str:
    if mime_type == "application/pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages).strip()
    if mime_type.startswith("image/"):
        return pytesseract.image_to_string(Image.open(path)).strip()
    if mime_type in {"text/plain", "text/markdown"}:
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError(f"Unsupported content type: {mime_type}")


def classify_document(text: str) -> tuple[DocumentType, float]:
    lower = text.lower()
    scores = {
        DocumentType.INVOICE: sum(word in lower for word in ("invoice", "amount due", "bill to", "invoice number")),
        DocumentType.RECEIPT: sum(word in lower for word in ("receipt", "cashier", "change", "thank you for your purchase")),
        DocumentType.RESUME: sum(word in lower for word in ("resume", "experience", "education", "skills", "employment")),
    }
    best_type, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score == 0:
        return DocumentType.GENERAL, 0.55
    return best_type, min(0.60 + best_score * 0.10, 0.95)


def extract_structured_data(text: str, document_type: DocumentType) -> dict:
    emails = sorted(set(EMAIL_RE.findall(text)))
    phones = sorted(set(match.strip() for match in PHONE_RE.findall(text)))
    dates = sorted(set(DATE_RE.findall(text)))
    result: dict = {"emails": emails, "phones": phones, "dates": dates}
    if document_type in {DocumentType.INVOICE, DocumentType.RECEIPT}:
        invoice = INVOICE_RE.search(text)
        total = MONEY_RE.search(text)
        result.update({"invoice_number": invoice.group(1) if invoice else None, "total": total.group(1).replace(",", "") if total else None})
    if document_type == DocumentType.RESUME:
        lower = text.lower()
        result["skills"] = sorted(skill for skill in SKILLS if skill in lower)
    return result


def process_file(path: Path, mime_type: str) -> tuple[str, DocumentType, float, dict]:
    text = extract_text(path, mime_type)
    if not text.strip():
        raise ValueError("No text could be extracted from the document")
    document_type, confidence = classify_document(text)
    data = extract_structured_data(text, document_type)
    return text, document_type, confidence, data
