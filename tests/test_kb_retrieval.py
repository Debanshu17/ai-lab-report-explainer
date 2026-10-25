"""Tests for Knowledge Base ingestion, alias resolution, and deterministic/vector retrieval."""

import pytest
from src.data.loaders import load_knowledge_base
from src.data.mapping import AliasResolver
from src.kb.ingest import create_all_chunks, chunk_blood_test, KBChunk
from src.kb.retriever import (
    DeterministicRetriever,
    VectorRetriever,
    UnifiedKBRetriever,
    FALLBACK_UNAVAILABLE_MESSAGE,
)


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


@pytest.fixture(scope="module")
def deterministic_retriever(kb):
    return DeterministicRetriever(kb=kb)


@pytest.fixture(scope="module")
def vector_retriever():
    return VectorRetriever()


@pytest.fixture(scope="module")
def unified_retriever(kb):
    return UnifiedKBRetriever(kb=kb)


def test_chunking_structure(kb):
    """Test that all blood tests and general topics are properly chunked."""
    chunks = create_all_chunks(kb)
    # 20 tests * 7 sections = 140; 5 general topics * 1 section = 5; total = 145
    assert len(chunks) == 145

    sections = {c.section for c in chunks}
    expected_sections = {
        "what_it_measures",
        "if_below_range",
        "if_above_range",
        "factors",
        "when_to_talk_to_a_doctor",
        "questions_for_doctor",
        "hindi_summary",
        "general_topic",
    }
    assert sections == expected_sections

    # Check metadata integrity
    for chunk in chunks:
        assert chunk.chunk_id
        assert chunk.test_id
        assert chunk.test_name
        assert chunk.text
        assert chunk.language in {"en", "hi"}
        meta = chunk.to_chroma_metadata()
        assert "sources_json" in meta
        assert "needs_verification" in meta


def test_deterministic_retriever_all_tests(deterministic_retriever, kb):
    """Verify 100% direct lookup coverage for all KB tests without embeddings."""
    for test in kb.blood_tests:
        retrieved = deterministic_retriever.get_test(test.test_id)
        assert retrieved is not None
        assert retrieved.test_id == test.test_id
        assert retrieved.test_name == test.test_name


def test_deterministic_explanation_context_low_high_normal(deterministic_retriever):
    """Verify structured context generation adheres to flag conditions."""
    # Test LOW
    ctx_low = deterministic_retriever.get_explanation_context("HEMOGLOBIN", "LOW")
    assert ctx_low is not None
    assert ctx_low["flag"] == "LOW"
    assert len(ctx_low["flag_context"]) > 0
    assert "below" in ctx_low["flag_context"].lower() or "low" in ctx_low["flag_context"].lower()
    assert len(ctx_low["sources"]) > 0
    assert ctx_low["needs_verification"] is True

    # Test HIGH
    ctx_high = deterministic_retriever.get_explanation_context("HEMOGLOBIN", "HIGH")
    assert ctx_high is not None
    assert ctx_high["flag"] == "HIGH"
    assert len(ctx_high["flag_context"]) > 0

    # Test NORMAL
    ctx_normal = deterministic_retriever.get_explanation_context("HEMOGLOBIN", "NORMAL")
    assert ctx_normal is not None
    assert ctx_normal["flag"] == "NORMAL"
    assert ctx_normal["flag_context"] == ""


def test_alias_resolution_100_percent(kb):
    """Verify that 100% of canonical names and aliases resolve correctly."""
    resolver = AliasResolver(kb)
    for test in kb.blood_tests:
        all_variants = [test.test_id, test.test_name] + test.aliases
        for var in all_variants:
            resolved_id = resolver.resolve(var)
            assert resolved_id == test.test_id, f"Variant '{var}' failed to resolve to '{test.test_id}'"


def test_vector_retriever_top_hit(vector_retriever):
    """Verify vector search accurately retrieves matching tests for free-text queries."""
    res = vector_retriever.query("What does hemoglobin measure?", n_results=1)
    assert len(res) == 1
    assert res[0].test_id == "HEMOGLOBIN"
    assert res[0].similarity >= 0.70
    assert res[0].section in {"what_it_measures", "general_topic"}


def test_vector_retriever_ungrounded_fallback(vector_retriever, unified_retriever):
    """Verify that ungrounded queries trigger fallback when similarity < 0.65."""
    # Complete nonsense query
    res, is_fallback = vector_retriever.query_with_fallback(
        "Recipe for chocolate brownies with powdered sugar", min_similarity=0.65
    )
    assert is_fallback is True
    assert len(res) == 0

    # Test unified retrieve_for_test on out-of-KB test
    unified_res = unified_retriever.retrieve_for_test("Troponin-I High Sensitivity")
    assert unified_res["is_fallback"] is True
    assert unified_res["what_it_measures"] == FALLBACK_UNAVAILABLE_MESSAGE
