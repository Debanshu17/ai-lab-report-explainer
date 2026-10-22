"""Deterministic alias to canonical test_id resolver.

Case-, punctuation-, and spacing-insensitive mapping.
Fails loudly if an alias maps to multiple tests or if a CSV test name has no match.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from src.data.models import KnowledgeBase, KBBloodTest
from src.data.loaders import load_knowledge_base


def normalize_alias(name: str) -> str:
    """Normalize alias name by lowercasing, stripping punctuation, and collapsing whitespace.

    Examples:
        'S. Creatinine' -> 's creatinine'
        'Urea (BUN)' -> 'urea bun'
        'Vitamin D, 25-OH' -> 'vitamin d 25 oh'
    """
    if not name:
        return ""
    lowered = name.lower()
    # Replace non-alphanumeric characters with space
    cleaned = re.sub(r"[^a-z0-9\s]", " ", lowered)
    # Collapse multiple whitespaces
    return " ".join(cleaned.split())


class AliasResolver:
    """Deterministic resolver mapping raw lab test names and aliases to canonical test_id."""

    def __init__(self, kb: Optional[KnowledgeBase] = None):
        self._kb = kb or load_knowledge_base()
        self._alias_to_test_id: dict[str, str] = {}
        self._test_id_to_test: dict[str, KBBloodTest] = {}
        self._build_index()

    def _build_index(self) -> None:
        """Populate alias index and assert collision freedom."""
        collisions: list[str] = []

        for test in self._kb.blood_tests:
            self._test_id_to_test[test.test_id] = test
            # Names include canonical test_id, test_name, and all aliases
            all_variants = [test.test_id, test.test_name] + test.aliases
            for variant in all_variants:
                norm_key = normalize_alias(variant)
                if not norm_key:
                    continue

                if norm_key in self._alias_to_test_id:
                    existing_id = self._alias_to_test_id[norm_key]
                    if existing_id != test.test_id:
                        collisions.append(
                            f"Collision on alias '{variant}' (normalized: '{norm_key}'): "
                            f"maps to both '{existing_id}' and '{test.test_id}'"
                        )
                else:
                    self._alias_to_test_id[norm_key] = test.test_id

        if collisions:
            raise ValueError(f"Knowledge Base alias collisions detected:\n" + "\n".join(collisions))

    def resolve(self, name: str) -> Optional[str]:
        """Resolve a test name to its canonical test_id, or None if unmatched."""
        norm_key = normalize_alias(name)
        return self._alias_to_test_id.get(norm_key)

    def resolve_strict(self, name: str) -> str:
        """Resolve a test name or raise KeyError if unmatched."""
        tid = self.resolve(name)
        if tid is None:
            raise KeyError(f"Test name '{name}' (normalized: '{normalize_alias(name)}') has no matching test_id.")
        return tid

    def get_test(self, test_id: str) -> Optional[KBBloodTest]:
        """Retrieve KBBloodTest by its canonical test_id."""
        return self._test_id_to_test.get(test_id)

    def validate_csv_test_names(self, test_names: Iterable[str]) -> None:
        """Validate that all test names in a collection match a canonical test_id.

        Raises:
            ValueError: If one or more test names fail to resolve.
        """
        unmatched = [name for name in set(test_names) if self.resolve(name) is None]
        if unmatched:
            raise ValueError(f"The following CSV test names have no matching Knowledge Base test_id: {unmatched}")

    @property
    def total_aliases(self) -> int:
        return len(self._alias_to_test_id)
