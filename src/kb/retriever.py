"""Knowledge Base retrieval system: deterministic lookup and Chroma vector retrieval.

Primary path: Deterministic direct dictionary lookup by test_id from AliasResolver
(fast, reproducible, zero embeddings required).

Secondary path: Chroma vector retrieval with BAAI/bge-small-en-v1.5 for unmatched
free-text queries and follow-up Q&A. Enforces a strict cosine similarity threshold (>= 0.65);
returns a safe fallback if ungrounded.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field

import chromadb

from src.config import settings
from src.data.mapping import AliasResolver
from src.data.models import KnowledgeBase, KBBloodTest, KBSource
from src.data.loaders import load_knowledge_base
from src.kb.ingest import (
    COLLECTION_NAME,
    get_embedding_function,
    ingest_knowledge_base,
)

logger = logging.getLogger(__name__)

FALLBACK_UNAVAILABLE_MESSAGE = (
    "No trusted explanation available for this test; discuss with your doctor."
)


class RetrievedChunk(BaseModel):
    """Retrieved Knowledge Base chunk with source provenance and similarity score."""

    chunk_id: str
    test_id: str
    test_name: str
    section: str
    language: str
    text: str
    similarity: float = Field(ge=0.0, le=1.0, description="Cosine similarity score (0.0 to 1.0)")
    sources: list[KBSource] = Field(default_factory=list)
    source_names: str = "None"
    source_urls: str = "None"
    source_verification: str = "unverified"
    needs_verification: bool = True


class DeterministicRetriever:
    """Primary retriever using deterministic in-memory dictionary lookup.
    
    Zero embeddings required. Exact, instantaneous, and 100% reproducible.
    """

    def __init__(self, kb: Optional[KnowledgeBase] = None, resolver: Optional[AliasResolver] = None):
        self._kb = kb or load_knowledge_base()
        self._resolver = resolver or AliasResolver(self._kb)
        self._tests_by_id: dict[str, KBBloodTest] = {t.test_id: t for t in self._kb.blood_tests}

    def get_test(self, test_id: str) -> Optional[KBBloodTest]:
        """Direct dictionary lookup by canonical test_id."""
        return self._tests_by_id.get(test_id)

    def resolve_and_get(self, test_name: str) -> Optional[KBBloodTest]:
        """Resolve raw test name or alias and retrieve KBBloodTest."""
        canonical_id = self._resolver.resolve(test_name)
        if canonical_id is None:
            return None
        return self._tests_by_id.get(canonical_id)

    def get_explanation_context(self, test_id: str, flag: str) -> Optional[dict[str, Any]]:
        """Retrieve structured medical explanation context for a flagged test.
        
        Args:
            test_id: Canonical test ID.
            flag: Flag string (LOW, HIGH, NORMAL, etc.)
            
        Returns:
            Dictionary with strictly grounded KB fields, or None if test_id unknown.
        """
        test = self.get_test(test_id)
        if test is None:
            return None

        # Determine flag-specific context
        flag_upper = flag.strip().upper()
        if flag_upper == "LOW":
            flag_context = test.general_context_low
        elif flag_upper == "HIGH":
            flag_context = test.general_context_high
        else:
            flag_context = ""

        return {
            "test_id": test.test_id,
            "test_name": test.test_name,
            "test_name_hindi": test.test_name_hindi,
            "test_name_transliteration": test.test_name_transliteration,
            "category": test.category,
            "standard_unit": test.standard_unit,
            "flag": flag_upper,
            "what_it_measures": test.clinical_summary,
            "flag_context": flag_context,
            "factors": test.factors_that_can_affect_result,
            "when_to_talk_to_a_doctor": test.when_to_talk_to_a_doctor,
            "questions_for_doctor": test.questions_for_doctor,
            "hindi_summary": test.hindi_summary,
            "sources": test.sources,
            "needs_verification": test.needs_verification,
            "hindi_reviewed": test.hindi_reviewed,
        }


class VectorRetriever:
    """Secondary retriever using Chroma vector store and BAAI/bge-small-en-v1.5 embeddings.
    
    Used for unmatched test names and free-form patient follow-up Q&A.
    Strictly enforces cosine similarity threshold.
    """

    def __init__(
        self,
        persist_dir: Optional[Path] = None,
        min_similarity: float = settings.EMBEDDING_SIMILARITY_THRESHOLD,
    ):
        self.directory = persist_dir or settings.CHROMA_PERSIST_DIRECTORY
        self.min_similarity = min_similarity
        self._ef = get_embedding_function()
        self._client = chromadb.PersistentClient(path=str(self.directory))
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Ensure the collection exists; if missing or empty, trigger ingestion."""
        try:
            self._collection = self._client.get_collection(
                name=COLLECTION_NAME,
                embedding_function=self._ef,
            )
            if self._collection.count() == 0:
                logger.info("Collection is empty; running automatic ingestion...")
                ingest_knowledge_base(persist_dir=self.directory)
                self._collection = self._client.get_collection(
                    name=COLLECTION_NAME,
                    embedding_function=self._ef,
                )
        except Exception:
            logger.info("Collection '%s' not found; running automatic ingestion...", COLLECTION_NAME)
            ingest_knowledge_base(persist_dir=self.directory)
            self._collection = self._client.get_collection(
                name=COLLECTION_NAME,
                embedding_function=self._ef,
            )

    def query(
        self,
        query_text: str,
        n_results: int = 3,
        min_similarity: Optional[float] = None,
        filter_metadata: Optional[dict[str, Any]] = None,
    ) -> list[RetrievedChunk]:
        """Search the vector store for semantic matches above the similarity threshold.
        
        Args:
            query_text: Query string.
            n_results: Maximum chunks to retrieve.
            min_similarity: Minimum cosine similarity threshold (default 0.65).
            filter_metadata: Chroma metadata filter dictionary (e.g. {"language": "en"}).
            
        Returns:
            List of RetrievedChunk instances meeting the similarity threshold, sorted by score.
        """
        threshold = self.min_similarity if min_similarity is None else min_similarity
        cleaned_query = query_text.strip()
        if not cleaned_query:
            return []

        query_kwargs: dict[str, Any] = {
            "query_texts": [cleaned_query],
            "n_results": n_results,
        }
        if filter_metadata:
            query_kwargs["where"] = filter_metadata

        results = self._collection.query(**query_kwargs)

        retrieved: list[RetrievedChunk] = []

        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        ids = results["ids"][0]
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]

        for cid, doc, meta, dist in zip(ids, docs, metas, distances):
            # Chroma with cosine distance: distance = 1 - cosine_similarity
            # Therefore similarity = 1.0 - distance
            similarity = round(max(0.0, min(1.0, 1.0 - dist)), 4)
            if similarity < threshold:
                continue

            sources: list[KBSource] = []
            if "sources_json" in meta and meta["sources_json"]:
                try:
                    s_list = json.loads(meta["sources_json"])
                    sources = [KBSource(**s) for s in s_list]
                except Exception:
                    pass

            retrieved.append(
                RetrievedChunk(
                    chunk_id=cid,
                    test_id=meta.get("test_id", ""),
                    test_name=meta.get("test_name", ""),
                    section=meta.get("section", ""),
                    language=meta.get("language", "en"),
                    text=doc,
                    similarity=similarity,
                    sources=sources,
                    source_names=meta.get("source_names", "None"),
                    source_urls=meta.get("source_urls", "None"),
                    source_verification=meta.get("source_verification", "unverified"),
                    needs_verification=bool(meta.get("needs_verification", True)),
                )
            )

        return retrieved

    def query_with_fallback(
        self,
        query_text: str,
        n_results: int = 3,
        min_similarity: Optional[float] = None,
    ) -> tuple[list[RetrievedChunk], bool]:
        """Query vector store and return (chunks, is_fallback).
        
        If no chunks pass the threshold, returns an empty list and True (indicating fallback).
        """
        chunks = self.query(query_text, n_results=n_results, min_similarity=min_similarity)
        if not chunks:
            return [], True
        return chunks, False


class UnifiedKBRetriever:
    """Unified retrieval interface combining deterministic lookup and vector search."""

    def __init__(
        self,
        kb: Optional[KnowledgeBase] = None,
        persist_dir: Optional[Path] = None,
        min_similarity: float = settings.EMBEDDING_SIMILARITY_THRESHOLD,
    ):
        self.deterministic = DeterministicRetriever(kb=kb)
        self.vector = VectorRetriever(persist_dir=persist_dir, min_similarity=min_similarity)

    def retrieve_for_test(
        self,
        test_name: str,
        flag: str = "NORMAL",
    ) -> dict[str, Any]:
        """Retrieve explanation context for a lab test.
        
        1. Attempts deterministic alias resolution first.
        2. If unmatched, checks for non-blood specimens (e.g. urine) and rejects them.
        3. Queries Chroma vector store with strict test-matching criteria.
        4. If similarity < threshold (or no trusted match), returns standard educational fallback.
        """
        # Step 1: Deterministic lookup (exact & alias-based)
        test = self.deterministic.resolve_and_get(test_name)
        if test is not None:
            ctx = self.deterministic.get_explanation_context(test.test_id, flag)
            if ctx is not None:
                ctx["retrieval_method"] = "deterministic"
                ctx["is_fallback"] = False
                return ctx

        # Step 2: Guard against uncurated non-blood tests (e.g. Urine Glucose, Urine Protein)
        clean_lower = test_name.lower()
        if "urine" in clean_lower or "stool" in clean_lower or "swab" in clean_lower:
            return self._build_fallback_context(test_name, flag)

        # Step 3: Vector search for candidate test strictly against test identity
        # Require similarity >= 0.72 against what_it_measures to prevent false guesses
        chunks = self.vector.query(
            test_name,
            n_results=1,
            min_similarity=0.72,
            filter_metadata={"section": "what_it_measures"},
        )
        if chunks:
            top = chunks[0]
            if top.test_id in self.deterministic._tests_by_id:
                ctx = self.deterministic.get_explanation_context(top.test_id, flag)
                if ctx is not None:
                    ctx["retrieval_method"] = "vector_candidate"
                    ctx["vector_similarity"] = top.similarity
                    ctx["is_fallback"] = False
                    return ctx

        # Step 4: Ungrounded fallback
        return self._build_fallback_context(test_name, flag)

    def _build_fallback_context(self, test_name: str, flag: str) -> dict[str, Any]:
        """Build a safe, educational fallback context when no trusted explanation is available."""
        return {
            "test_id": "UNKNOWN",
            "test_name": test_name,
            "test_name_hindi": "",
            "test_name_transliteration": "",
            "category": "Unknown",
            "standard_unit": "",
            "flag": flag,
            "what_it_measures": FALLBACK_UNAVAILABLE_MESSAGE,
            "flag_context": "",
            "factors": [],
            "when_to_talk_to_a_doctor": "Discuss this test and its result with your healthcare provider.",
            "questions_for_doctor": [f"What does the '{test_name}' test measure and what does my result mean?"],
            "hindi_summary": "",
            "sources": [],
            "needs_verification": True,
            "hindi_reviewed": False,
            "retrieval_method": "fallback",
            "is_fallback": True,
        }

    def answer_question(self, question: str, n_chunks: int = 3) -> dict[str, Any]:
        """Retrieve relevant KB chunks to answer a patient's educational question."""
        chunks, is_fallback = self.vector.query_with_fallback(question, n_results=n_chunks)
        if is_fallback:
            return {
                "question": question,
                "is_fallback": True,
                "fallback_message": FALLBACK_UNAVAILABLE_MESSAGE,
                "chunks": [],
            }

        return {
            "question": question,
            "is_fallback": False,
            "fallback_message": "",
            "chunks": [c.model_dump() for c in chunks],
        }
