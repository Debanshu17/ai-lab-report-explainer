"""Evaluation and benchmarking script for Knowledge Base retrieval.

Evaluates:
1. Alias resolution accuracy across all KB aliases (Target: 100%).
2. Top-1 vector retrieval accuracy across 30 free-text queries covering all 20 tests and 5 topics.
3. Fallback behavior on ungrounded queries (< 0.65 threshold) and uncurated report tests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.data.loaders import load_knowledge_base
from src.data.mapping import AliasResolver
from src.kb.ingest import ingest_knowledge_base
from src.kb.retriever import DeterministicRetriever, VectorRetriever, UnifiedKBRetriever, FALLBACK_UNAVAILABLE_MESSAGE

# 30 Natural free-text patient queries mapped to exact canonical test_id / topic_id
FREE_TEXT_BENCHMARK_QUERIES = [
    # Hemoglobin & Complete Blood Count (CBC)
    ("what does hemoglobin measure in blood?", "HEMOGLOBIN"),
    ("meaning of low hb level", "HEMOGLOBIN"),
    ("what is hematocrit or pcv?", "HEMATOCRIT"),
    ("red blood cell count meaning", "RBC"),
    ("what is total leukocyte count TLC?", "WBC"),
    ("low platelet count significance", "PLATELETS"),
    ("what does MCV mean in a blood report?", "MCV"),
    ("causes of high white blood cell count", "WBC"),

    # Liver Function Panel
    ("what is SGPT test for?", "ALT"),
    ("why is ALT alanine aminotransferase high?", "ALT"),
    ("what does SGOT AST indicate?", "AST"),
    ("what is serum bilirubin test?", "BILIRUBIN"),

    # Kidney Function Panel
    ("what is serum creatinine test?", "CREATININE"),
    ("elevated creatinine kidney function", "CREATININE"),
    ("what does BUN blood urea nitrogen tell?", "UREA"),

    # Metabolic & Lipid Panel
    ("fasting blood glucose meaning", "FASTING_GLUCOSE"),
    ("what causes high fasting blood sugar?", "FASTING_GLUCOSE"),
    ("what is HbA1c test for diabetes?", "HBA1C"),
    ("what does high total cholesterol mean?", "TOTAL_CHOLESTEROL"),
    ("good cholesterol HDL levels", "HDL"),
    ("bad cholesterol LDL meaning", "LDL"),
    ("elevated triglycerides in lipid profile", "TRIGLYCERIDES"),

    # Thyroid & Vitamin Panels
    ("what does TSH thyroid stimulating hormone do?", "TSH"),
    ("low vitamin D 25-OH meaning", "VITAMIN_D"),
    ("vitamin B12 deficiency blood test", "VITAMIN_B12"),

    # General Educational Topics
    ("why do reference ranges differ between labs?", "WHY_RANGES_DIFFER"),
    ("what does an out of range lab result mean?", "OUT_OF_RANGE_MEANING"),
    ("do I need to fast before a blood test?", "FASTING_BEFORE_TEST"),
    ("when should I seek urgent medical care?", "URGENT_MEDICAL_CARE"),
    ("why should a doctor interpret my lab report?", "PROFESSIONAL_INTERPRETATION"),
]

# Non-medical queries that MUST trigger vector threshold fallback (< 0.65)
UNGROUNDED_VECTOR_QUERIES = [
    "How to bake a chocolate cake recipe",
    "Stock market forecast for next week",
    "Car tire replacement and automotive maintenance",
    "Python programming tutorial for beginners",
    "Weather forecast for tomorrow afternoon",
]

# Uncurated lab report tests that MUST return fallback context
UNCURATED_REPORT_TESTS = [
    "Urine Glucose",
    "Urine Protein",
    "Troponin I High Sensitivity",
    "EKG Electrocardiogram",
    "Chest X-Ray",
]


def run_alias_resolution_benchmark(kb, resolver: AliasResolver) -> dict[str, Any]:
    """Test resolution of every alias across all blood tests in KB."""
    total_aliases = 0
    correct = 0
    failures = []

    for test in kb.blood_tests:
        variants = [test.test_id, test.test_name] + test.aliases
        for var in variants:
            total_aliases += 1
            resolved = resolver.resolve(var)
            if resolved == test.test_id:
                correct += 1
            else:
                failures.append((var, test.test_id, resolved))

    accuracy = (correct / total_aliases) * 100.0 if total_aliases > 0 else 0.0
    return {
        "total_alias_variants": total_aliases,
        "correct": correct,
        "accuracy_pct": accuracy,
        "failures": failures,
    }


def run_free_text_retrieval_benchmark(vector_retriever: VectorRetriever) -> dict[str, Any]:
    """Test top-1 and top-3 retrieval accuracy on benchmark queries."""
    total = len(FREE_TEXT_BENCHMARK_QUERIES)
    top_1_hits = 0
    top_3_hits = 0
    details = []

    for query, expected_id in FREE_TEXT_BENCHMARK_QUERIES:
        chunks = vector_retriever.query(query, n_results=3, min_similarity=0.0)
        hit_1 = False
        hit_3 = False
        top_id = chunks[0].test_id if chunks else None
        top_score = chunks[0].similarity if chunks else 0.0

        if chunks and chunks[0].test_id == expected_id:
            top_1_hits += 1
            hit_1 = True

        chunk_ids = [c.test_id for c in chunks]
        if expected_id in chunk_ids:
            top_3_hits += 1
            hit_3 = True

        details.append({
            "query": query,
            "expected": expected_id,
            "top_1": top_id,
            "top_score": top_score,
            "hit_1": hit_1,
            "hit_3": hit_3,
        })

    return {
        "total_queries": total,
        "top_1_hits": top_1_hits,
        "top_1_accuracy_pct": (top_1_hits / total) * 100.0,
        "top_3_hits": top_3_hits,
        "top_3_accuracy_pct": (top_3_hits / total) * 100.0,
        "details": details,
    }


def run_ungrounded_fallback_benchmark(
    vector_retriever: VectorRetriever,
    unified: UnifiedKBRetriever,
) -> dict[str, Any]:
    """Test fallback triggering on queries outside KB."""
    vector_results = []
    vector_all_correct = True
    for q in UNGROUNDED_VECTOR_QUERIES:
        chunks, is_fallback = vector_retriever.query_with_fallback(q, min_similarity=0.65)
        correct = is_fallback and len(chunks) == 0
        if not correct:
            vector_all_correct = False
        vector_results.append({
            "query": q,
            "is_fallback": is_fallback,
            "correct": correct,
        })

    report_test_results = []
    report_all_correct = True
    for t in UNCURATED_REPORT_TESTS:
        res = unified.retrieve_for_test(t)
        correct = res["is_fallback"] and res["what_it_measures"] == FALLBACK_UNAVAILABLE_MESSAGE
        if not correct:
            report_all_correct = False
        report_test_results.append({
            "test_name": t,
            "is_fallback": res["is_fallback"],
            "correct": correct,
        })

    return {
        "vector_queries_tested": len(UNGROUNDED_VECTOR_QUERIES),
        "vector_all_correct": vector_all_correct,
        "vector_results": vector_results,
        "report_tests_tested": len(UNCURATED_REPORT_TESTS),
        "report_all_correct": report_all_correct,
        "report_results": report_test_results,
    }


def main():
    print("=" * 60)
    print("PHASE 4: KNOWLEDGE BASE INGESTION & RETRIEVAL EVALUATION")
    print("=" * 60)

    kb = load_knowledge_base()
    print(f"Loaded Knowledge Base: {len(kb.blood_tests)} tests, {len(kb.general_topics)} topics.")

    # 1. Ingestion
    print("\n[Step 1] Ingesting Knowledge Base into Chroma DB...")
    num_chunks = ingest_knowledge_base(kb, force_recreate=True)
    print(f"Ingestion complete: {num_chunks} chunks stored.")

    # 2. Alias resolution benchmark
    print("\n[Step 2] Benchmarking deterministic alias resolution...")
    resolver = AliasResolver(kb)
    alias_results = run_alias_resolution_benchmark(kb, resolver)
    print(f"Total Alias Variants Tested: {alias_results['total_alias_variants']}")
    print(f"Correct Resolutions: {alias_results['correct']}")
    print(f"Alias Resolution Accuracy: {alias_results['accuracy_pct']:.2f}%")
    if alias_results["failures"]:
        print("Failures:", alias_results["failures"])

    # 3. Vector retrieval benchmark
    print("\n[Step 3] Benchmarking Chroma vector retrieval (BAAI/bge-small-en-v1.5)...")
    vector_retriever = VectorRetriever()
    vector_results = run_free_text_retrieval_benchmark(vector_retriever)
    print(f"Total Free-Text Queries: {vector_results['total_queries']}")
    print(f"Top-1 Hits: {vector_results['top_1_hits']} ({vector_results['top_1_accuracy_pct']:.2f}%)")
    print(f"Top-3 Hits: {vector_results['top_3_hits']} ({vector_results['top_3_accuracy_pct']:.2f}%)")

    for d in vector_results["details"]:
        status = "PASS" if d["hit_1"] else "FAIL"
        print(f"  [{status}] '{d['query']}' -> Top: {d['top_1']} (score: {d['top_score']:.3f}, expected: {d['expected']})")

    # 4. Ungrounded fallback benchmark
    print("\n[Step 4] Benchmarking ungrounded fallback (< 0.65 threshold & uncurated tests)...")
    unified = UnifiedKBRetriever(kb)
    fallback_results = run_ungrounded_fallback_benchmark(vector_retriever, unified)
    print(f"Non-medical Queries Tested: {fallback_results['vector_queries_tested']}")
    print(f"  All Triggered Fallback (< 0.65): {fallback_results['vector_all_correct']}")
    print(f"Uncurated Report Tests Tested: {fallback_results['report_tests_tested']}")
    print(f"  All Triggered Fallback: {fallback_results['report_all_correct']}")

    print("\n" + "=" * 60)
    print("PHASE 4 EVALUATION SUMMARY:")
    print(f"  - Ingested Chunks: {num_chunks}")
    print(f"  - Alias Resolution Accuracy: {alias_results['accuracy_pct']:.2f}% (Target: 100%)")
    print(f"  - Top-1 Vector Retrieval Accuracy: {vector_results['top_1_accuracy_pct']:.2f}%")
    print(f"  - Top-3 Vector Retrieval Accuracy: {vector_results['top_3_accuracy_pct']:.2f}%")
    print(f"  - Vector Threshold Reliability (<0.65): {'100%' if fallback_results['vector_all_correct'] else 'Failed'}")
    print(f"  - Uncurated Test Fallback Reliability: {'100%' if fallback_results['report_all_correct'] else 'Failed'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
