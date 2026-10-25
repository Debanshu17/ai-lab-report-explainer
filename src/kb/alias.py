"""Alias resolution interface for the Knowledge Base.

Wraps deterministic alias mapping with convenient accessors and validation.
"""

from __future__ import annotations

from typing import Optional
from src.data.mapping import AliasResolver, normalize_alias
from src.data.models import KnowledgeBase, KBBloodTest

_DEFAULT_RESOLVER: Optional[AliasResolver] = None


def get_default_resolver() -> AliasResolver:
    """Get or create singleton AliasResolver."""
    global _DEFAULT_RESOLVER
    if _DEFAULT_RESOLVER is None:
        _DEFAULT_RESOLVER = AliasResolver()
    return _DEFAULT_RESOLVER


def resolve_test_id(name: str, resolver: Optional[AliasResolver] = None) -> Optional[str]:
    """Resolve raw test name or alias to canonical test_id."""
    r = resolver or get_default_resolver()
    return r.resolve(name)


def get_test_by_id(test_id: str, resolver: Optional[AliasResolver] = None) -> Optional[KBBloodTest]:
    """Get KBBloodTest model by canonical test_id."""
    r = resolver or get_default_resolver()
    return r.get_test(test_id)


def get_all_aliases(resolver: Optional[AliasResolver] = None) -> dict[str, str]:
    """Return dictionary of normalized alias -> canonical test_id."""
    r = resolver or get_default_resolver()
    return dict(r._alias_to_test_id)
