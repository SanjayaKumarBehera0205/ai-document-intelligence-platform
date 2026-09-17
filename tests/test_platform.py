from app.models import DocumentType
from app.processor import classify_document, extract_structured_data


def test_authentication_required(client):
    assert client.get("/api/v1/documents").status_code == 401


def test_invoice_upload_and_extraction(client, auth):
    text = b"INVOICE\nInvoice Number: INV-2026-01\nAmount Due: 1,250.50\nContact billing@example.com\nDate 2026-09-17"
    response = client.post("/api/v1/documents", headers=auth, files={"file": ("invoice.txt", text, "text/plain")})
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["document_type"] == "invoice"
    assert payload["extracted_data"]["invoice_number"] == "INV-2026-01"
    assert payload["extracted_data"]["total"] == "1250.50"


def test_resume_classification_and_skills():
    text = "Resume Experience Education Skills Python FastAPI Docker Machine Learning"
    doc_type, confidence = classify_document(text)
    assert doc_type == DocumentType.RESUME
    assert confidence >= 0.8
    data = extract_structured_data(text, doc_type)
    assert "python" in data["skills"]
    assert "fastapi" in data["skills"]


def test_search_dashboard_and_delete(client, auth):
    client.post("/api/v1/documents", headers=auth, files={"file": ("resume.txt", b"Resume Skills Python Django Experience Education", "text/plain")})
    listed = client.get("/api/v1/documents?search=Python", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    document_id = listed.json()["items"][0]["id"]
    dashboard = client.get("/api/v1/dashboard", headers=auth).json()
    assert dashboard["completed"] == 1
    assert dashboard["by_type"]["resume"] == 1
    assert client.delete(f"/api/v1/documents/{document_id}", headers=auth).status_code == 204


def test_rejects_unsupported_file(client, auth):
    response = client.post("/api/v1/documents", headers=auth, files={"file": ("data.exe", b"binary", "application/octet-stream")})
    assert response.status_code == 415
