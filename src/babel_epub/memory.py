"""Lightweight translation memory for cross-book reuse.

The store is deliberately dependency-light: one JSON file per project/series,
written atomically. Segment entries are keyed by a stable hash of source_html
when available, falling back to source_text. Callers still validate structural
compatibility before trusting a hit.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MEMORY_VERSION = 1
DEFAULT_MEMORY_PROJECT_ID = "default"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_memory_project_id(value: str | None) -> str:
    raw = (value or DEFAULT_MEMORY_PROJECT_ID).strip() or DEFAULT_MEMORY_PROJECT_ID
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip(".-_")
    return slug[:80] or DEFAULT_MEMORY_PROJECT_ID


def memory_path_for(data_dir: Path, project_id: str | None = None, memory_path: str | Path | None = None) -> Path:
    if memory_path:
        return Path(memory_path)
    project = normalize_memory_project_id(project_id)
    return Path(data_dir) / "translation_memory" / f"{project}.json"


def source_key(row: dict[str, Any]) -> str:
    value = str(row.get("source_html") or row.get("source_text") or "").strip()
    compact = re.sub(r"\s+", " ", value)
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MemoryLookup:
    row: dict[str, str]
    entry: dict[str, Any]


class TranslationMemoryStore:
    def __init__(self, path: Path, project_id: str | None = None) -> None:
        self.path = Path(path)
        self.project_id = normalize_memory_project_id(project_id or self.path.stem)
        self._lock = threading.RLock()
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": MEMORY_VERSION, "project_id": self.project_id, "segments": {}, "term_decisions": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": MEMORY_VERSION, "project_id": self.project_id, "segments": {}, "term_decisions": {}}
        if not isinstance(data, dict):
            return {"version": MEMORY_VERSION, "project_id": self.project_id, "segments": {}, "term_decisions": {}}
        data.setdefault("version", MEMORY_VERSION)
        data.setdefault("project_id", self.project_id)
        data.setdefault("segments", {})
        data.setdefault("term_decisions", {})
        if isinstance(data.get("segments"), list):
            data["segments"] = {
                str(entry.get("source_hash") or source_key(entry)): entry
                for entry in data["segments"]
                if isinstance(entry, dict)
            }
        if not isinstance(data.get("segments"), dict):
            data["segments"] = {}
        if not isinstance(data.get("term_decisions"), dict):
            data["term_decisions"] = {}
        return data

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = dict(self._data)
            payload["version"] = MEMORY_VERSION
            payload["project_id"] = self.project_id
            tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp_path.replace(self.path)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": True,
                "project_id": self.project_id,
                "path": str(self.path),
                "segment_entries": len(self._data.get("segments", {})),
                "term_decisions": len(self._data.get("term_decisions", {})),
            }

    def lookup(self, source_row: dict[str, Any], target_language: str) -> MemoryLookup | None:
        key = source_key(source_row)
        with self._lock:
            entry = self._data.get("segments", {}).get(key)
            if not isinstance(entry, dict):
                return None
            if str(entry.get("target_language", "")) != str(target_language):
                return None
            translated_html = entry.get("translated_html")
            if not isinstance(translated_html, str) or not translated_html.strip():
                return None
            return MemoryLookup(row={"id": str(source_row.get("id", "")), "translated_html": translated_html}, entry=dict(entry))

    def upsert_segment(
        self,
        source_row: dict[str, Any],
        translated_row: dict[str, Any],
        *,
        target_language: str,
        source_project: str = "",
        confidence: float = 1.0,
    ) -> bool:
        translated_html = translated_row.get("translated_html")
        if not isinstance(translated_html, str) or not translated_html.strip():
            return False
        key = source_key(source_row)
        now = utc_now()
        entry = {
            "source_hash": key,
            "source_text": str(source_row.get("source_text", "")),
            "source_html": str(source_row.get("source_html", "")),
            "translated_html": translated_html,
            "target_language": str(target_language),
            "source_project": source_project or self.project_id,
            "confidence": float(confidence),
            "updated_at": now,
        }
        with self._lock:
            previous = self._data.setdefault("segments", {}).get(key)
            if isinstance(previous, dict) and all(
                previous.get(field) == entry[field]
                for field in ("source_text", "source_html", "translated_html", "target_language", "source_project")
            ):
                return False
            self._data["segments"][key] = entry
            return True

    def upsert_rows(
        self,
        source_rows: Iterable[dict[str, Any]],
        translated_rows: Iterable[dict[str, Any]],
        *,
        target_language: str,
        source_project: str = "",
    ) -> int:
        translated_by_id = {str(row.get("id", "")): row for row in translated_rows}
        count = 0
        for source in source_rows:
            row = translated_by_id.get(str(source.get("id", "")))
            if row and self.upsert_segment(source, row, target_language=target_language, source_project=source_project):
                count += 1
        if count:
            self.save()
        return count

    def export_to(self, destination: Path) -> Path:
        self.save()
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return destination

    def import_from(self, source: Path) -> dict[str, int]:
        imported = 0
        skipped = 0
        entries = _read_memory_entries(Path(source))
        with self._lock:
            segments = self._data.setdefault("segments", {})
            for entry in entries:
                if not isinstance(entry, dict):
                    skipped += 1
                    continue
                key = str(entry.get("source_hash") or source_key(entry))
                translated_html = entry.get("translated_html")
                if not key or not isinstance(translated_html, str) or not translated_html.strip():
                    skipped += 1
                    continue
                normalized = dict(entry)
                normalized["source_hash"] = key
                normalized.setdefault("target_language", "Simplified Chinese")
                normalized.setdefault("source_project", self.project_id)
                normalized.setdefault("confidence", 1.0)
                normalized.setdefault("updated_at", utc_now())
                segments[key] = normalized
                imported += 1
        if imported:
            self.save()
        return {"imported": imported, "skipped": skipped}


def _read_memory_entries(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return []
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        rows = []
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    if isinstance(parsed, dict):
        segments = parsed.get("segments") or parsed.get("entries") or []
        if isinstance(segments, dict):
            return [entry for entry in segments.values() if isinstance(entry, dict)]
        if isinstance(segments, list):
            return [entry for entry in segments if isinstance(entry, dict)]
    return []
