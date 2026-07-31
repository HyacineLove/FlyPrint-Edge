"""Session-scoped ownership for PRP files downloaded to the Edge."""

from __future__ import annotations

import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
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
            self._selections[session_id] = {
                **public,
                "source_path": source,
            }
            return deepcopy(public)

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
            self._remove_empty_parent(Path(selection["source_path"]).parent)
            return True

    def clear_session(self, session_id: str) -> bool:
        with self._lock:
            selection = self._selections.pop(session_id, None)
        if not selection:
            return False
        self._delete_source(Path(selection["source_path"]))
        return True

    @staticmethod
    def _validate_id(value: str) -> None:
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise ValueError("invalid PRP session or file id")

    def _delete_source(self, source: Path) -> None:
        source.unlink(missing_ok=True)
        Path(str(source) + ".part").unlink(missing_ok=True)
        self._remove_empty_parent(source.parent)

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
