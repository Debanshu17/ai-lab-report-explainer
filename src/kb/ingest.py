"""Knowledge Base chunking and Chroma DB ingestion.

Chunks curated blood tests and general topics into semantic units,
attaching source provenance, verification flags, and section metadata.
Guarantees idempotent ingestion.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

import chromadb
from chromadb.utils import embedding_functions

from src.config import settings
from src.data.models import KnowledgeBase, KBBloodTest, KBGeneralTopic, KBSource
from src.data.loaders import load_knowledge_base

logger = logging.getLogger(__name__)

COLLECTION_NAME = "lab_knowledge_base"


class KBChunk(BaseModel):
    """Semantic chunk from the Knowledge Base with rich metadata and provenance."""

    chunk_id: str = Field(description="Unique chunk identifier, e.g. HEMOGLOBIN_what_it_measures")
    test_id: str = Field(description="Canonical test_id or topic_id")
    test_name: str = Field(description="Display test name or topic title")
    section: str = Field(
        description="Section: what_it_measures, if_below_range, if_above_range, factors, when_to_talk_to_a_doctor, questions_for_doctor, general_topic, hindi_summary"
    )
    language: str = Field(default="en", description="ISO language code, 'en' or 'hi'")
    text: str = Field(description="Searchable chunk body text")
    sources: list[KBSource] = Field(default_factory=list, description="Original source references")
    needs_verification: bool = Field(description="Whether this entry still requires human verification")

    def to_chroma_metadata(self) -> dict[str, str | int | float | bool]:
        """Convert chunk fields into Chroma-compatible primitive metadata."""
        sources_dicts = [s.model_dump() for s in self.sources]
        source_names = "; ".join(s.source_name for s in self.sources) if self.sources else "None"
        source_urls = "; ".join(s.url for s in self.sources) if self.sources else "None"
        # Dominant or list of verifications
        verifs = "; ".join(s.verification for s in self.sources) if self.sources else "unverified"

        return {
            "chunk_id": self.chunk_id,
            "test_id": self.test_id,
            "test_name": self.test_name,
            "section": self.section,
            "language": self.language,
            "source_names": source_names,
            "source_urls": source_urls,
            "source_verification": verifs,
            "sources_json": json.dumps(sources_dicts, ensure_ascii=False),
            "needs_verification": self.needs_verification,
        }


def chunk_blood_test(test: KBBloodTest) -> list[KBChunk]:
    """Split a single KBBloodTest into semantic chunks."""
    chunks: list[KBChunk] = []

    # 1. What it measures (clinical summary + test identity)
    aliases_str = ", ".join(test.aliases) if test.aliases else "None"
    measures_text = (
        f"{test.test_name} ({test.category})\n"
        f"Aliases: {aliases_str}\n"
        f"Standard unit: {test.standard_unit}\n\n"
        f"What it measures:\n{test.clinical_summary}"
    )
    chunks.append(
        KBChunk(
            chunk_id=f"{test.test_id}_what_it_measures",
            test_id=test.test_id,
            test_name=test.test_name,
            section="what_it_measures",
            language="en",
            text=measures_text.strip(),
            sources=test.sources,
            needs_verification=test.needs_verification,
        )
    )

    # 2. If below range (general_context_low)
    below_text = (
        f"{test.test_name} - Below Reference Range (Low Result):\n"
        f"{test.general_context_low}"
    )
    chunks.append(
        KBChunk(
            chunk_id=f"{test.test_id}_if_below_range",
            test_id=test.test_id,
            test_name=test.test_name,
            section="if_below_range",
            language="en",
            text=below_text.strip(),
            sources=test.sources,
            needs_verification=test.needs_verification,
        )
    )

    # 3. If above range (general_context_high)
    above_text = (
        f"{test.test_name} - Above Reference Range (High Result):\n"
        f"{test.general_context_high}"
    )
    chunks.append(
        KBChunk(
            chunk_id=f"{test.test_id}_if_above_range",
            test_id=test.test_id,
            test_name=test.test_name,
            section="if_above_range",
            language="en",
            text=above_text.strip(),
            sources=test.sources,
            needs_verification=test.needs_verification,
        )
    )

    # 4. Factors affecting result
    factors_list = "\n".join(f"- {factor}" for factor in test.factors_that_can_affect_result)
    factors_text = (
        f"{test.test_name} - Factors That Can Affect the Result:\n"
        f"{factors_list}"
    )
    chunks.append(
        KBChunk(
            chunk_id=f"{test.test_id}_factors",
            test_id=test.test_id,
            test_name=test.test_name,
            section="factors",
            language="en",
            text=factors_text.strip(),
            sources=test.sources,
            needs_verification=test.needs_verification,
        )
    )

    # 5. When to talk to a doctor
    doctor_text = (
        f"{test.test_name} - When to Talk to a Doctor:\n"
        f"{test.when_to_talk_to_a_doctor}"
    )
    chunks.append(
        KBChunk(
            chunk_id=f"{test.test_id}_when_to_talk_to_a_doctor",
            test_id=test.test_id,
            test_name=test.test_name,
            section="when_to_talk_to_a_doctor",
            language="en",
            text=doctor_text.strip(),
            sources=test.sources,
            needs_verification=test.needs_verification,
        )
    )

    # 6. Questions for doctor
    questions_list = "\n".join(f"- {q}" for q in test.questions_for_doctor)
    questions_text = (
        f"{test.test_name} - Suggested Questions for Your Doctor:\n"
        f"{questions_list}"
    )
    chunks.append(
        KBChunk(
            chunk_id=f"{test.test_id}_questions_for_doctor",
            test_id=test.test_id,
            test_name=test.test_name,
            section="questions_for_doctor",
            language="en",
            text=questions_text.strip(),
            sources=test.sources,
            needs_verification=test.needs_verification,
        )
    )

    # 7. Hindi summary
    hindi_text = (
        f"{test.test_name} ({test.test_name_hindi} / {test.test_name_transliteration})\n\n"
        f"{test.hindi_summary}"
    )
    chunks.append(
        KBChunk(
            chunk_id=f"{test.test_id}_hindi_summary",
            test_id=test.test_id,
            test_name=test.test_name,
            section="hindi_summary",
            language="hi",
            text=hindi_text.strip(),
            sources=test.sources,
            needs_verification=test.needs_verification,
        )
    )

    return chunks


def chunk_general_topic(topic: KBGeneralTopic) -> KBChunk:
    """Create a semantic chunk for an educational general topic."""
    text = f"{topic.title}\n\n{topic.summary}"
    return KBChunk(
        chunk_id=f"{topic.topic_id}_overview",
        test_id=topic.topic_id,
        test_name=topic.title,
        section="general_topic",
        language="en",
        text=text.strip(),
        sources=topic.sources,
        needs_verification=topic.needs_verification,
    )


def create_all_chunks(kb: Optional[KnowledgeBase] = None) -> list[KBChunk]:
    """Generate all chunks from Knowledge Base blood tests and general topics."""
    base_kb = kb or load_knowledge_base()
    all_chunks: list[KBChunk] = []

    for test in base_kb.blood_tests:
        all_chunks.extend(chunk_blood_test(test))

    for topic in base_kb.general_topics:
        all_chunks.append(chunk_general_topic(topic))

    return all_chunks


def get_embedding_function():
    """Build SentenceTransformer embedding function with configured model."""
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=settings.EMBEDDING_MODEL
    )


def ingest_knowledge_base(
    kb: Optional[KnowledgeBase] = None,
    persist_dir: Optional[Path] = None,
    force_recreate: bool = True,
) -> int:
    """Ingest Knowledge Base chunks into persistent Chroma vector store.

    Args:
        kb: KnowledgeBase instance (loads default if None).
        persist_dir: Path for Chroma persistent directory (uses settings if None).
        force_recreate: If True, deletes any existing collection to guarantee idempotency.

    Returns:
        int: Number of chunks ingested.
    """
    directory = persist_dir or settings.CHROMA_PERSIST_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(directory))
    ef = get_embedding_function()

    if force_recreate:
        try:
            client.delete_collection(name=COLLECTION_NAME)
            logger.info("Deleted existing Chroma collection '%s' for clean re-ingestion.", COLLECTION_NAME)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    chunks = create_all_chunks(kb)

    ids = [c.chunk_id for c in chunks]
    documents = [c.text for c in chunks]
    metadatas = [c.to_chroma_metadata() for c in chunks]

    # Ingest in batch
    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    logger.info("Successfully ingested %d chunks into Chroma collection '%s'.", len(chunks), COLLECTION_NAME)
    return len(chunks)
