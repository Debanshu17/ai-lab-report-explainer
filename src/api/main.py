"""FastAPI application for AI Lab Report Explainer.

Endpoints:
- GET  /health: System health and Knowledge Base status
- GET  /tests: Catalog of supported blood tests and aliases
- POST /explain: In-memory PDF upload and structured educational report generation
- POST /ask: Scope-restricted educational follow-up Q&A
"""

from __future__ import annotations

import io
from typing import Any, List, Optional
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import pymupdf

from src.config import settings, get_logger
from src.data.loaders import load_knowledge_base
from src.extraction.pipeline import run_extraction_pipeline
from src.flagging.flagger import flag_test_result
from src.explain.explainer import DualModeExplainer
from src.explain.schema import ReportExplanation
from src.kb.retriever import UnifiedKBRetriever, FALLBACK_UNAVAILABLE_MESSAGE
from src.safety.scope import is_question_in_scope, CANNED_OUT_OF_SCOPE_MESSAGE
from src.safety.rules import is_safe_explanation
from src.llm.client import LLMClient

logger = get_logger(__name__)

app = FastAPI(
    title="AI Lab Report Explainer API",
    description="Educational laboratory test report explanation and safety layer API.",
    version="1.0.0",
)

# Enable CORS for local Streamlit and frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global singletons
_KB = None
_EXPLAINER = None
_RETRIEVER = None


def get_kb():
    global _KB
    if _KB is None:
        _KB = load_knowledge_base()
    return _KB


def get_retriever():
    global _RETRIEVER
    if _RETRIEVER is None:
        _RETRIEVER = UnifiedKBRetriever(kb=get_kb())
    return _RETRIEVER


def get_explainer():
    global _EXPLAINER
    if _EXPLAINER is None:
        _EXPLAINER = DualModeExplainer(retriever=get_retriever())
    return _EXPLAINER


class AskRequest(BaseModel):
    """Schema for follow-up patient question."""

    question: str = Field(description="Patient's free-text educational question")
    report_tests: List[str] = Field(
        default_factory=list,
        description="List of test names or IDs present on the patient's report",
    )
    language: str = Field(default="en", description="Preferred response language: 'en' or 'hi'")


class AskResponse(BaseModel):
    """Response schema for follow-up question."""

    in_scope: bool
    answer: str
    is_fallback: bool
    sources: List[dict] = Field(default_factory=list)


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """System health check and configuration summary."""
    kb = get_kb()
    return {
        "status": "ok",
        "provider": settings.LLM_PROVIDER,
        "model": settings.LLM_MODEL,
        "temperature": settings.LLM_TEMPERATURE,
        "kb_tests_loaded": len(kb.blood_tests),
        "kb_topics_loaded": len(kb.general_topics),
        "version": "1.0.0",
    }


@app.get("/tests", status_code=status.HTTP_200_OK)
def list_supported_tests():
    """List all supported blood tests, standard units, categories, and aliases."""
    kb = get_kb()
    catalog = []
    for test in kb.blood_tests:
        catalog.append({
            "test_id": test.test_id,
            "test_name": test.test_name,
            "test_name_hindi": test.test_name_hindi,
            "test_name_transliteration": test.test_name_transliteration,
            "category": test.category,
            "standard_unit": test.standard_unit,
            "aliases": test.aliases,
            "needs_verification": test.needs_verification,
        })
    return {"total_tests": len(catalog), "tests": catalog}


@app.post("/explain", status_code=status.HTTP_200_OK)
async def explain_report_endpoint(
    file: UploadFile = File(...),
    language: str = Form("en"),
    mode: str = Form("kb_template"),
):
    """Process uploaded lab report in-memory and return structured educational explanation."""
    # 1. Read bytes in-memory (zero disk persistence)
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # 2. File size validation (<= 5 MB)
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(pdf_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB} MB.",
        )

    # 3. Magic bytes validation
    if not pdf_bytes.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. File must be a valid PDF document.",
        )

    # 4. Page count validation (<= 10 pages)
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(doc)
        doc.close()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to read PDF document: {e}",
        )

    if page_count > settings.MAX_PDF_PAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PDF exceeds page limit ({page_count} > {settings.MAX_PDF_PAGES}).",
        )

    # 5. Extraction Pipeline
    try:
        extraction_res = run_extraction_pipeline(pdf_bytes)
    except Exception as e:
        logger.error("Extraction pipeline failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing PDF content.",
        )

    if not extraction_res.validation.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=extraction_res.validation.error_message or "PDF validation failed.",
        )

    # 6. Flag test rows deterministically against printed reference ranges
    flagged_rows = []
    for r in extraction_res.rows:
        flag_res = flag_test_result(
            value=r.numeric_value,
            value_text=r.raw_value_text,
            range_text=r.normalized_range_text,
            patient_sex=extraction_res.patient_context.gender,
            test_id=r.canonical_test_id,
            unit=r.normalized_unit,
        )
        flagged_rows.append({
            "name": r.raw_test_name,
            "value": r.numeric_value,
            "unit": r.normalized_unit,
            "reference_interval": r.normalized_range_text,
            "flag": flag_res.flag,
        })

    # 7. Generate Educational Explanation
    explainer = get_explainer()
    explanation: ReportExplanation = explainer.explain_report(
        extracted_rows=flagged_rows,
        mode=mode,
        language=language,
    )

    return {
        "explanation": explanation.model_dump(),
        "patient_context": extraction_res.patient_context.model_dump(),
        "extraction_summary": {
            "total_extracted": extraction_res.total_rows,
            "parsed_rows": extraction_res.parsed_rows,
            "unparsed_rows": extraction_res.unparsed_rows,
            "mode_used": extraction_res.mode_used,
        },
    }


@app.post("/ask", response_model=AskResponse, status_code=status.HTTP_200_OK)
def ask_question_endpoint(req: AskRequest):
    """Answer patient follow-up question strictly within report scope and KB grounding."""
    # 1. Scope restriction check
    in_scope, reason = is_question_in_scope(req.question, req.report_tests)
    if not in_scope:
        return AskResponse(
            in_scope=False,
            answer=CANNED_OUT_OF_SCOPE_MESSAGE,
            is_fallback=True,
            sources=[],
        )

    # 2. Vector search in KB
    retriever = get_retriever()
    chunks, is_fallback = retriever.vector.query_with_fallback(
        query_text=req.question,
        n_results=3,
        min_similarity=settings.EMBEDDING_SIMILARITY_THRESHOLD,
    )

    if is_fallback or not chunks:
        return AskResponse(
            in_scope=True,
            answer=FALLBACK_UNAVAILABLE_MESSAGE,
            is_fallback=True,
            sources=[],
        )

    # 3. Grounded response assembly
    sources_dicts = []
    context_snippets = []
    for c in chunks:
        context_snippets.append(f"[{c.test_name} - {c.section}]: {c.text}")
        for s in c.sources:
            sources_dicts.append({
                "source_name": s.source_name,
                "url": s.url,
                "verification": s.verification,
            })

    # Deduplicate sources
    seen_urls = set()
    unique_sources = []
    for s in sources_dicts:
        if s["url"] not in seen_urls:
            seen_urls.add(s["url"])
            unique_sources.append(s)

    kb_context = "\n\n".join(context_snippets)

    # Generate grounded answer
    try:
        llm = LLMClient()
        prompt = f"""You are an educational laboratory report explainer answering a patient's question.

CORE SAFETY RULES:
1. Answer ONLY using the curated Knowledge Base context below.
2. Do NOT diagnose or say what illness the user has.
3. Do NOT recommend medications, dosages, or treatments.
4. Do NOT use reassurance terms ("fine", "don't worry") or alarm terms ("serious", "danger").
5. Keep the explanation educational and encourage consulting their physician.

PATIENT QUESTION: {req.question}

CURATED KNOWLEDGE BASE CONTEXT:
{kb_context}
"""
        raw_answer = llm.generate_raw(prompt)
        is_safe, violations = is_safe_explanation(raw_answer)
        if not is_safe:
            logger.warning("Q&A answer violated safety scanner: %s. Using chunk text.", violations)
            raw_answer = f"Educational context from verified medical references:\n\n{chunks[0].text}"

    except Exception:
        # Fallback to direct chunk text if LLM unavailable
        raw_answer = f"Educational context from verified medical references:\n\n{chunks[0].text}"

    return AskResponse(
        in_scope=True,
        answer=raw_answer,
        is_fallback=False,
        sources=unique_sources,
    )
