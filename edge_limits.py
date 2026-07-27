"""Local Edge limits used after Cloud delivery and during preview preparation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


# 0 means that a local limit is disabled. The page default is the policy
# agreed for this phase; it remains configurable through the Edge admin panel.
DEFAULT_MAX_FILE_SIZE_BYTES = 0
DEFAULT_MAX_DOCUMENT_PAGES = 5
DEFAULT_MAX_LIST_ITEMS = 0


class EdgeLimitExceeded(ValueError):
    """A local Edge policy rejected a document before it enters printing."""


def normalize_local_limits(settings: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """Return stable, non-negative local limits from the Edge settings section."""
    source = settings if isinstance(settings, dict) else {}
    return {
        "max_file_size_bytes": _non_negative_int(
            source.get("max_file_size_bytes"), DEFAULT_MAX_FILE_SIZE_BYTES
        ),
        "max_document_pages": _non_negative_int(
            source.get("max_document_pages"), DEFAULT_MAX_DOCUMENT_PAGES
        ),
        "max_list_items": _non_negative_int(
            source.get("max_list_items"), DEFAULT_MAX_LIST_ITEMS
        ),
    }


def validate_file_size(path: Path, settings: Optional[Dict[str, Any]]) -> Optional[str]:
    """Reject a downloaded source when its local Edge size limit is exceeded."""
    limit = normalize_local_limits(settings)["max_file_size_bytes"]
    if limit <= 0:
        return None
    if path.stat().st_size > limit:
        return "文件超过 Edge 本地大小限制"
    return None


def validate_page_count(page_count: int, settings: Optional[Dict[str, Any]]) -> Optional[str]:
    """Reject a canonical document when its local Edge page limit is exceeded."""
    limit = normalize_local_limits(settings)["max_document_pages"]
    if limit <= 0:
        return None
    if page_count > limit:
        return "文件页数超过 Edge 本地页数限制"
    return None


def _non_negative_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default
