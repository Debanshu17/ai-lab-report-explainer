"""Clinical unit validation and formula conversions.

Enforces:
- Unit sanity validation against KB standard and alternate units
- Warnings on unexpected or mismatched units
- Implementation of the official IFCC HbA1c conversion formula
- RULE: Never convert silently for flagging; flagging is evaluated strictly
  against the printed range.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from src.data.loaders import load_knowledge_base
from src.data.models import KnowledgeBase, KBBloodTest


def convert_hba1c_percent_to_mmol_mol(percent: float) -> float:
    """Convert HbA1c from NGSP percentage (%) to IFCC (mmol/mol).

    Official IFCC formula: (percent - 2.15) * 10.93
    """
    return round((percent - 2.15) * 10.93, 1)


def convert_hba1c_mmol_mol_to_percent(mmol_mol: float) -> float:
    """Convert HbA1c from IFCC (mmol/mol) to NGSP percentage (%).

    Official reverse formula: (mmol_mol / 10.93) + 2.15
    """
    return round((mmol_mol / 10.93) + 2.15, 2)


def check_unit_compatibility(
    test_id: Optional[str],
    unit: str,
    kb: Optional[KnowledgeBase] = None,
) -> Tuple[bool, Optional[str]]:
    """Validate a unit against the Knowledge Base standard and alternate units.

    Returns:
        (is_compatible, warning_message)
    """
    if not test_id or not unit:
        return True, None

    loaded_kb = kb or load_knowledge_base()
    test_entry: Optional[KBBloodTest] = next(
        (t for t in loaded_kb.blood_tests if t.test_id == test_id), None
    )

    if not test_entry:
        return True, None

    clean_unit = unit.strip().lower()
    std_unit = test_entry.standard_unit.strip().lower()

    # Exact or normalized match to standard unit
    if clean_unit == std_unit:
        return True, None

    # Check alternate units defined in KB
    for alt in test_entry.alternate_units:
        if clean_unit == alt.unit.strip().lower():
            return True, None

    # Handle micro sign representations
    clean_unit_mu = clean_unit.replace("\u03bc", "\u00b5")
    std_unit_mu = std_unit.replace("\u03bc", "\u00b5")
    if clean_unit_mu == std_unit_mu:
        return True, None

    warning = (
        f"Unit '{unit}' differs from standard Knowledge Base unit '{test_entry.standard_unit}' "
        f"for test {test_entry.test_name}."
    )
    return False, warning
