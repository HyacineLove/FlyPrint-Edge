"""Session- and Provider-scoped ownership for PRP files downloaded to Edge."""

from __future__ import annotations

import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MAX_CACHED_SOURCES_PER_SESSION = 8
_PUBLIC_FIELDS = {"id": "file_id", "name": "file_name", "media_type": "file_type", "size": "size", "sha256": "content_hash"}


class PRPFileSelectionManager:
    def __init__(self, temporary_root: Path):
        self._root = Path(temporary_root).resolve() / "prp-selections"
        self._lock = threading.RLock()
        self._selections: Dict[str, Dict[str, Any]] = {}
        self._cached_sources: Dict[str, Dict[str, Dict[str, Any]]] = {}

    @staticmethod
    def _cache_key(provider_id: str, file_id: str) -> str:
        return provider_id + ":" + file_id

    def destination_for(self, session_id: str, file_id: str, provider_id: str = "default") -> Path:
        self._validate_id(session_id)
        self._validate_id(file_id)
        self._validate_id(provider_id)
        directory = self._root / session_id / provider_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{file_id}.source"

    def bind(self, session_id: str, metadata: Dict[str, Any], source_path: Path, provider_id: str = "default") -> Dict[str, Any]:
        self._validate_id(session_id)
        self._validate_id(provider_id)
        source = Path(source_path).resolve()
        expected_parent = (self._root / session_id / provider_id).resolve()
        if source.parent != expected_parent or not source.is_file():
            raise ValueError("PRP source is outside its session/provider directory")
        public = {"source_origin": "prp", "provider_id": provider_id}
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
                self._cached_sources.get(session_id, {}).pop(self._cache_key(previous["provider_id"], previous["file_id"]), None)
            self._selections[session_id] = {**public, "source_path": source}
            return deepcopy(public)

    def release_selection(self, session_id: str) -> Optional[str]:
        with self._lock:
            selection = self._selections.pop(session_id, None)
            if not selection:
                return None
            cached = self._cached_sources.setdefault(session_id, {})
            key = self._cache_key(selection["provider_id"], selection["file_id"])
            cached[key] = deepcopy(selection)
            self._enforce_cache_limit(session_id, key)
            return str(selection["file_id"])

    def activate_cached(self, session_id: str, file_id: str, provider_id: str = "default") -> Optional[Dict[str, Any]]:
        self._validate_id(session_id)
        self._validate_id(file_id)
        self._validate_id(provider_id)
        with self._lock:
            key = self._cache_key(provider_id, file_id)
            cached = self._cached_sources.get(session_id, {}).get(key)
            if not cached:
                return None
            if not Path(cached["source_path"]).is_file():
                self._cached_sources.get(session_id, {}).pop(key, None)
                return None
            current = self._selections.get(session_id)
            if current and (current["file_id"] != file_id or current["provider_id"] != provider_id):
                current_key = self._cache_key(current["provider_id"], current["file_id"])
                self._cached_sources.setdefault(session_id, {})[current_key] = deepcopy(current)
                self._enforce_cache_limit(session_id, key)
            self._selections[session_id] = deepcopy(cached)
            return {key: deepcopy(value) for key, value in cached.items() if key != "source_path"}

    def get_source(self, session_id: str, file_id: str, provider_id: str = "default") -> Optional[Path]:
        with self._lock:
            selection = self._selections.get(session_id)
            if not selection or selection["file_id"] != file_id or selection.get("provider_id") != provider_id:
                return None
            source = Path(selection["source_path"])
            return source if source.is_file() else None

    def snapshot(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            selection = self._selections.get(session_id)
            return {} if not selection else {key: deepcopy(value) for key, value in selection.items() if key != "source_path"}

    def release(self, session_id: str, file_id: str, provider_id: str = "default") -> bool:
        with self._lock:
            selection = self._selections.get(session_id)
            if not selection or selection["file_id"] != file_id or selection.get("provider_id") != provider_id:
                return False
            del self._selections[session_id]
            self._cached_sources.get(session_id, {}).pop(self._cache_key(provider_id, file_id), None)
            source = Path(selection["source_path"])
        self._delete_source(source)
        return True

    def clear_session(self, session_id: str) -> bool:
        with self._lock:
            selection = self._selections.pop(session_id, None)
            cached = self._cached_sources.pop(session_id, {})
        paths = {str(item["source_path"]) for item in cached.values()}
        if selection:
            paths.add(str(selection["source_path"]))
        for raw_path in paths:
            self._delete_source(Path(raw_path))
        return bool(paths)

    @staticmethod
    def _validate_id(value: str) -> None:
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise ValueError("invalid PRP session, provider, or file id")

    def _enforce_cache_limit(self, session_id: str, keep_key: str) -> None:
        cached = self._cached_sources.get(session_id)
        while cached and len(cached) > _MAX_CACHED_SOURCES_PER_SESSION:
            oldest_key = next(iter(cached))
            if oldest_key == keep_key and len(cached) > 1:
                oldest_key = next(iter(list(cached)[1:]))
            entry = cached.pop(oldest_key)
            self._delete_source(Path(entry["source_path"]))

    def _delete_source(self, source: Path) -> None:
        source.unlink(missing_ok=True)
        Path(str(source) + ".part").unlink(missing_ok=True)
        provider_dir = source.parent
        session_dir = provider_dir.parent
        for directory in (provider_dir, session_dir, self._root):
            try:
                directory.rmdir()
            except OSError:
                break
