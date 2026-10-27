"""Tests for FastAPI endpoints (Phase 7).

Covers:
- GET /health: health status and KB statistics
- GET /tests: complete catalog of supported blood tests and aliases
- POST /explain: multipart in-memory PDF upload, PII stripping, deterministic flagging, and structured explanations
- POST /explain validations: empty file, non-PDF, and size limit rejection (413)
- POST /explain in Hindi: verifies Devanagari localization and unreviewed banner
- POST /ask: in-scope educational Q&A with KB citations
- POST /ask: out-of-scope symptom and drug rejection (canned message)
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.safety.scope import CANNED_OUT_OF_SCOPE_MESSAGE
from src.explain.hindi import HINDI_UNREVIEWED_NOTICE

client = TestClient(app)

SAMPLE_DEV_PDF_PATH = Path("data/synthetic/reports/REPORT_003.pdf")


def test_get_health():
    """Verify system health endpoint returns correct operational state."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["kb_tests_loaded"] == 20
    assert data["kb_topics_loaded"] == 5
    assert "provider" in data
    assert "model" in data


def test_get_tests():
    """Verify supported tests catalog returns all 20 curated tests with aliases."""
    response = client.get("/tests")
    assert response.status_code == 200
    data = response.json()
    assert data["total_tests"] == 20
    tests = data["tests"]
    assert len(tests) == 20

    first_test = tests[0]
    assert "test_id" in first_test
    assert "test_name" in first_test
    assert "test_name_hindi" in first_test
    assert "aliases" in first_test
    assert "standard_unit" in first_test


def test_post_explain_dev_pdf_kb_template():
    """Verify in-memory PDF upload and structured report generation."""
    assert SAMPLE_DEV_PDF_PATH.exists(), f"Sample DEV report missing: {SAMPLE_DEV_PDF_PATH}"

    with open(SAMPLE_DEV_PDF_PATH, "rb") as f:
        pdf_bytes = f.read()

    response = client.post(
        "/explain",
        files={"file": ("REPORT_003.pdf", pdf_bytes, "application/pdf")},
        data={"language": "en", "mode": "kb_template"},
    )
    assert response.status_code == 200
    data = response.json()

    # Check top-level response structure
    assert "explanation" in data
    assert "patient_context" in data
    assert "extraction_summary" in data

    # Check PII redaction: only age and gender are passed; patient name and phone are absent
    p_ctx = data["patient_context"]
    assert "patient_name" not in p_ctx or p_ctx.get("patient_name") is None
    assert "phone" not in p_ctx or p_ctx.get("phone") is None
    assert "gender" in p_ctx

    # Check explanation structure
    expl = data["explanation"]
    assert expl["mode"] == "kb_template"
    assert expl["language"] == "en"
    assert "educational" in expl["disclaimer"].lower()
    assert len(expl["tests"]) > 0

    # Check individual test fields
    first_test = expl["tests"][0]
    assert "test_name" in first_test
    assert "flag" in first_test
    assert first_test["flag"] in {"NORMAL", "LOW", "HIGH", "NEEDS_REVIEW"}
    assert "what_it_measures" in first_test
    assert "what_your_value_means" in first_test
    assert "questions_for_doctor" in first_test
    assert len(first_test["questions_for_doctor"]) >= 1


def test_post_explain_hindi_mode():
    """Verify Hindi explanation generation via FastAPI endpoint."""
    with open(SAMPLE_DEV_PDF_PATH, "rb") as f:
        pdf_bytes = f.read()

    response = client.post(
        "/explain",
        files={"file": ("REPORT_003.pdf", pdf_bytes, "application/pdf")},
        data={"language": "hi", "mode": "kb_template"},
    )
    assert response.status_code == 200
    data = response.json()

    expl = data["explanation"]
    assert expl["language"] == "hi"
    assert "शैक्षणिक साधन है" in expl["disclaimer"]
    assert HINDI_UNREVIEWED_NOTICE in expl["summary"]


def test_post_explain_empty_file():
    """Verify rejection of empty file upload."""
    response = client.post(
        "/explain",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_post_explain_invalid_pdf():
    """Verify rejection of non-PDF file upload."""
    response = client.post(
        "/explain",
        files={"file": ("test.txt", b"Hello world, this is a plain text file.", "text/plain")},
    )
    assert response.status_code == 400
    assert "valid pdf" in response.json()["detail"].lower()


def test_post_explain_file_too_large():
    """Verify 413 rejection when file exceeds 5 MB."""
    # 6 MB dummy payload starting with %PDF-
    large_bytes = b"%PDF-" + b"0" * (6 * 1024 * 1024)
    response = client.post(
        "/explain",
        files={"file": ("large.pdf", large_bytes, "application/pdf")},
    )
    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"].lower()


def test_post_ask_in_scope():
    """Verify follow-up Q&A for in-scope question returns grounded answers."""
    req_body = {
        "question": "What does Hemoglobin measure in blood?",
        "report_tests": ["Hemoglobin", "Total Cholesterol"],
        "language": "en",
    }
    response = client.post("/ask", json=req_body)
    assert response.status_code == 200
    data = response.json()
    assert data["in_scope"] is True
    assert data["is_fallback"] is False
    assert len(data["answer"]) > 20
    assert len(data["sources"]) > 0


def test_post_ask_out_of_scope():
    """Verify immediate rejection of out-of-scope symptom or medication inquiries."""
    req_body = {
        "question": "My knee hurts after a soccer match, what painkiller should I take?",
        "report_tests": ["Hemoglobin"],
        "language": "en",
    }
    response = client.post("/ask", json=req_body)
    assert response.status_code == 200
    data = response.json()
    assert data["in_scope"] is False
    assert data["answer"] == CANNED_OUT_OF_SCOPE_MESSAGE
    assert data["sources"] == []
