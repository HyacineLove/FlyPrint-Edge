"""Session-scoped ownership for PRP files downloaded to the Edge."""

from __future__ import annotations

import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MAX_CACHED_SOURCES_PER_SESSION = 8
_PUBLIC_FIELDS = {
    "id": "file_id",
    "name": "file_name",
    "media_type": "file_type",
    "size": "size",
    "sha256": "content_hash",
}


class PRPFileSelectionManager:
    def __init__(self, temporary_root: Path):
        self._root = Path(temporary_root).resolve() / "prp-selections"
        self._lock = threading.RLock()
        self._selections: Dict[str, Dict[str, Any]] = {}
        # A session may leave the preview page and choose the same PRP file
        # again. Keep the downloaded source for that session so the second
        # selection does not fetch it from PRP again.
        self._cached_sources: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def destination_for(self, session_id: str, file_id: str) -> Path:
        self._validate_id(session_id)
        self._validate_id(file_id)
        directory = self._root / session_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{file_id}.source"

    def bind(
        self, session_id: str, metadata: Dict[str, Any], source_path: Path
    ) -> Dict[str, Any]:
        self._validate_id(session_id)
        source = Path(source_path).resolve()
        expected_parent = (self._root / session_id).resolve()
        if source.parent != expected_parent or not source.is_file():
            raise ValueError("PRP source is outside its session directory")
        public = {"source_origin": "prp"}
        for incoming, outgoing in _PUBLIC_FIELDS.items():
            value = metadata.get(incoming)
            if value in (None, ""):
                raise ValueError(f"missing PRP metadata: {incoming}")
            public[outgoing] = value
        if public["file_id"] != source.stem:
            raise ValueError("PRP file id does not match local source")

        with self._lock:
            previous = self._selections.get(session_id)
            if previous and previous["source_path"] != source:
                self._delete_source(Path(previous["source_path"]))
                self._cached_sources.get(session_id, {}).pop(previous["file_id"], None)
            self._selections[session_id] = {
                **public,
                "source_path": source,
            }
            return deepcopy(public)

    def release_selection(self, session_id: str) -> Optional[str]:
        """Leave the active file while retaining its source for this session."""
        with self._lock:
            selection = self._selections.pop(session_id, None)
            if not selection:
                return None
            cached = self._cached_sources.setdefault(session_id, {})
            cached[selection["file_id"]] = deepcopy(selection)
            self._enforce_cache_limit(session_id, keep_file_id=selection["file_id"])
            return str(selection["file_id"])

    def activate_cached(self, session_id: str, file_id: str) -> Optional[Dict[str, Any]]:
        """Re-bind a previously downloaded source if it is still present."""
        self._validate_id(session_id)
        self._validate_id(file_id)
        with self._lock:
            cached = self._cached_sources.get(session_id, {}).get(file_id)
            if not cached:
                return None
            source = Path(cached["source_path"])
            if not source.is_file():
                self._cached_sources.get(session_id, {}).pop(file_id, None)
                return None
            current = self._selections.get(session_id)
            if current and current["file_id"] != file_id:
                self._cached_sources.setdefault(session_id, {})[current["file_id"]] = deepcopy(current)
                self._enforce_cache_limit(session_id, keep_file_id=file_id)
            self._selections[session_id] = deepcopy(cached)
            return {
                key: deepcopy(value)
                for key, value in cached.items()
                if key != "source_path"
            }

    def get_source(self, session_id: str, file_id: str) -> Optional[Path]:
        with self._lock:
            selection = self._selections.get(session_id)
            if not selection or selection["file_id"] != file_id:
                return None
            source = Path(selection["source_path"])
            return source if source.is_file() else None

    def snapshot(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            selection = self._selections.get(session_id)
            if not selection:
                return {}
            return {
                key: deepcopy(value)
                for key, value in selection.items()
                if key != "source_path"
            }

    def release(self, session_id: str, file_id: str) -> bool:
        with self._lock:
            selection = self._selections.get(session_id)
            if not selection or selection["file_id"] != file_id:
                return False
            del self._selections[session_id]
            self._cached_sources.get(session_id, {}).pop(file_id, None)
            source = Path(selection["source_path"])
        # 锁外删除源文件（含 .part），幂等：预览流程已删除时 missing_ok 安全。
        # 修复预览中途出错时 .source 残留磁盘的问题。
        self._delete_source(source)
        return True

    def clear_session(self, session_id: str) -> bool:
        with self._lock:
            selection = self._selections.pop(session_id, None)
            cached = self._cached_sources.pop(session_id, {})
        paths = {str(item["source_path"]) for item in cached.values()}
        if selection:
            paths.add(str(selection["source_path"]))
        if not paths:
            return False
        for path in paths:
            self._delete_source(Path(path))
        return True

    @staticmethod
    def _validate_id(value: str) -> None:
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise ValueError("invalid PRP session or file id")

    def _delete_source(self, source: Path) -> None:
        source.unlink(missing_ok=True)
        Path(str(source) + ".part").unlink(missing_ok=True)
        self._remove_empty_parent(source.parent)

    def _enforce_cache_limit(self, session_id: str, keep_file_id: str) -> None:
        cached = self._cached_sources.get(session_id)
        if not cached:
            return
        while len(cached) > _MAX_CACHED_SOURCES_PER_SESSION:
            oldest_file_id = next(iter(cached))
            if oldest_file_id == keep_file_id and len(cached) > 1:
                oldest_file_id = next(iter(list(cached)[1:]))
            entry = cached.pop(oldest_file_id)
            self._delete_source(Path(entry["source_path"]))

    def _remove_empty_parent(self, directory: Path) -> None:
        if directory.parent == self._root and directory.exists():
            try:
                directory.rmdir()
            except OSError:
                return
        if self._root.exists():
            try:
                self._root.rmdir()
            except OSError:
                pass
