"""Knowledge Base ingestion, alias resolution, and retrieval package."""

from src.kb.alias import AliasResolver, normalize_alias
from src.kb.ingest import ingest_knowledge_base, KBChunk
from src.kb.retriever import DeterministicRetriever, VectorRetriever, UnifiedKBRetriever, RetrievedChunk

__all__ = [
    "AliasResolver",
    "normalize_alias",
    "ingest_knowledge_base",
    "KBChunk",
    "DeterministicRetriever",
    "VectorRetriever",
    "UnifiedKBRetriever",
    "RetrievedChunk",
]
