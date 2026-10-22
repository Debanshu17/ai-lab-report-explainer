"""Tests for CSV and KB loaders, data models, and alias resolver."""

from __future__ import annotations

import pytest
from pathlib import Path

from src.data.loaders import load_csv_lab_database, load_knowledge_base
from src.data.mapping import AliasResolver, normalize_alias
from src.data.models import CSVLabRow, KnowledgeBase, KBBloodTest


def test_load_csv_lab_database_success():
    """Verify that the CSV loads exactly 300 valid rows across 15 patients."""
    rows = load_csv_lab_database()
    assert len(rows) == 300

    patients = {r.Patient_ID for r in rows}
    assert len(patients) == 15

    tests = {r.Test_Name for r in rows}
    assert len(tests) == 20

    # Ensure every row passes model validation
    for r in rows:
        assert isinstance(r, CSVLabRow)
        assert r.Age > 0
        assert r.Gender in {"Male", "Female"}
        assert len(r.Reference_Interval) > 0


def test_load_csv_missing_file(tmp_path: Path):
    """Verify FileNotFoundError is raised if CSV file is missing."""
    with pytest.raises(FileNotFoundError):
        load_csv_lab_database(tmp_path / "nonexistent.csv")


def test_load_csv_invalid_header(tmp_path: Path):
    """Verify ValueError is raised if CSV is missing required columns."""
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("Patient_ID,Test_Name\nP001,Hemoglobin\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required headers"):
        load_csv_lab_database(bad_csv)


def test_load_knowledge_base_success():
    """Verify Knowledge Base loads 20 blood tests and 5 general topics."""
    kb = load_knowledge_base()
    assert isinstance(kb, KnowledgeBase)
    assert len(kb.blood_tests) == 20
    assert len(kb.general_topics) == 5

    # Check non-negotiable metadata requirements
    for bt in kb.blood_tests:
        assert isinstance(bt, KBBloodTest)
        assert bt.needs_verification is True
        assert bt.hindi_reviewed is False
        assert len(bt.plausible_value_bounds) == 2
        assert bt.plausible_value_bounds[0] < bt.plausible_value_bounds[1]

    # Verify URGENT_MEDICAL_CARE topic
    urgent_topic = next((t for t in kb.general_topics if t.topic_id == "URGENT_MEDICAL_CARE"), None)
    assert urgent_topic is not None
    assert len(urgent_topic.sources) == 0  # Known open item


def test_load_kb_missing_file(tmp_path: Path):
    """Verify FileNotFoundError if KB JSON does not exist."""
    with pytest.raises(FileNotFoundError):
        load_knowledge_base(tmp_path / "missing.json")


def test_load_kb_invalid_json(tmp_path: Path):
    """Verify ValueError on corrupted JSON."""
    corrupt_json = tmp_path / "corrupt.json"
    corrupt_json.write_text("{ broken json: ", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_knowledge_base(corrupt_json)


def test_normalize_alias():
    """Verify alias normalization strips punctuation and collapses spacing."""
    assert normalize_alias("Hb") == "hb"
    assert normalize_alias("  Haemoglobin  ") == "haemoglobin"
    assert normalize_alias("S. Creatinine") == "s creatinine"
    assert normalize_alias("Urea (BUN)") == "urea bun"
    assert normalize_alias("Vitamin D, 25-OH") == "vitamin d 25 oh"
    assert normalize_alias("") == ""


def test_alias_resolver_coverage():
    """Verify all 20 CSV test names resolve deterministically."""
    resolver = AliasResolver()
    csv_rows = load_csv_lab_database()

    for r in csv_rows:
        tid = resolver.resolve(r.Test_Name)
        assert tid is not None, f"Failed to resolve CSV test: {r.Test_Name}"
        assert resolver.resolve_strict(r.Test_Name) == tid


def test_alias_resolver_case_and_punctuation_invariance():
    """Verify resolver succeeds regardless of case, dots, brackets, hyphens."""
    resolver = AliasResolver()
    assert resolver.resolve("hb") == "HEMOGLOBIN"
    assert resolver.resolve("HAEMOGLOBIN") == "HEMOGLOBIN"
    assert resolver.resolve("s. creatinine") == "CREATININE"
    assert resolver.resolve("S. CREATININE") == "CREATININE"
    assert resolver.resolve("Urea (BUN)") == "UREA"
    assert resolver.resolve("urea bun") == "UREA"
    assert resolver.resolve("BUN") == "UREA"
    assert resolver.resolve("fasting glucose") == "FASTING_GLUCOSE"
    assert resolver.resolve("Unknown Test 12345") is None

    with pytest.raises(KeyError):
        resolver.resolve_strict("Unknown Test 12345")


def test_alias_resolver_detects_collision(monkeypatch):
    """Verify resolver raises ValueError if an alias collides across two tests."""
    kb = load_knowledge_base()
    # Artificially inject a duplicate alias into two tests
    fake_kb_data = kb.model_dump()
    fake_kb_data["blood_tests"][0]["aliases"].append("SHARED_COLLISION_ALIAS")
    fake_kb_data["blood_tests"][1]["aliases"].append("SHARED_COLLISION_ALIAS")
    tampered_kb = KnowledgeBase.model_validate(fake_kb_data)

    with pytest.raises(ValueError, match="Knowledge Base alias collisions detected"):
        AliasResolver(tampered_kb)


def test_boundary_rows_count():
    """Verify exactly 15 rows in CSV where Observed_Value == limit."""
    rows = load_csv_lab_database()
    boundary_count = 0
    for r in rows:
        parts = [float(p.strip()) for p in r.Reference_Interval.split("-")]
        if r.Observed_Value == parts[0] or r.Observed_Value == parts[1]:
            boundary_count += 1
    assert boundary_count == 15
