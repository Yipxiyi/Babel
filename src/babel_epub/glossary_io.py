"""Glossary import/export helpers.

Supported interchange formats are intentionally dependency-free:
- CSV with Babel glossary term columns.
- TBX-like XML using termEntry/langSet/tig/term.
- Markdown preset/prompt tables or pending-candidate bullets.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from .glossary import compact_glossary_terms, normalize_glossary_term


GLOSSARY_COLUMNS = [
    "source",
    "translation",
    "type",
    "aliases",
    "frequency",
    "evidence",
    "status",
    "confidence",
    "locked",
]


def glossary_format_for(path_or_format: str | Path | None, fallback: str = "csv") -> str:
    value = str(path_or_format or "").strip().lower()
    if value in {"csv", "tbx", "md", "markdown", "json", "preset"}:
        return "md" if value in {"markdown", "preset"} else value
    suffix = Path(value).suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix in {".tbx", ".xml"}:
        return "tbx"
    if suffix in {".md", ".markdown"}:
        return "md"
    if suffix == ".json":
        return "json"
    return fallback


def import_glossary_text(text: str, fmt: str = "csv", default_status: str = "pending") -> list[dict]:
    fmt = glossary_format_for(fmt, fallback="csv")
    if fmt == "csv":
        return import_glossary_csv(text, default_status=default_status)
    if fmt == "tbx":
        return import_glossary_tbx(text, default_status=default_status)
    if fmt == "md":
        return import_glossary_markdown(text, default_status=default_status)
    if fmt == "json":
        payload = json.loads(text or "[]")
        if isinstance(payload, dict):
            payload = payload.get("terms", [])
        if not isinstance(payload, list):
            raise ValueError("glossary JSON must be a list or an object with a terms list")
        return compact_glossary_terms([_with_default_status(row, default_status) for row in payload if isinstance(row, dict)])
    raise ValueError(f"unsupported glossary import format: {fmt}")


def export_glossary_text(terms: list[dict], fmt: str = "csv", target_language: str = "Simplified Chinese") -> str:
    fmt = glossary_format_for(fmt, fallback="csv")
    normalized = compact_glossary_terms(terms)
    if fmt == "csv":
        return export_glossary_csv(normalized)
    if fmt == "tbx":
        return export_glossary_tbx(normalized, target_language=target_language)
    if fmt == "md":
        return export_glossary_markdown(normalized, target_language=target_language)
    if fmt == "json":
        return json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    raise ValueError(f"unsupported glossary export format: {fmt}")


def import_glossary_file(path: Path, default_status: str = "pending", fmt: str | None = None) -> list[dict]:
    selected = fmt or glossary_format_for(path)
    return import_glossary_text(Path(path).read_text(encoding="utf-8"), selected, default_status=default_status)


def export_glossary_file(path: Path, terms: list[dict], target_language: str = "Simplified Chinese", fmt: str | None = None) -> Path:
    selected = fmt or glossary_format_for(path)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(export_glossary_text(terms, selected, target_language=target_language), encoding="utf-8")
    return path


def merge_glossary_terms(existing: list[dict], imported: list[dict], mode: str = "upsert") -> list[dict]:
    if mode not in {"replace", "append", "upsert"}:
        raise ValueError("merge mode must be replace, append, or upsert")
    if mode == "replace":
        return compact_glossary_terms(imported)
    if mode == "append":
        return compact_glossary_terms(existing + imported)
    by_source = {term["source"]: term for term in compact_glossary_terms(existing)}
    for term in compact_glossary_terms(imported):
        previous = by_source.get(term["source"])
        if previous:
            merged = dict(previous)
            merged.update({key: value for key, value in term.items() if value not in ("", [], None)})
            if previous.get("locked") and not term.get("locked"):
                merged["locked"] = True
            if previous.get("status") == "approved" and term.get("status") == "pending":
                merged["status"] = "approved"
            by_source[term["source"]] = merged
        else:
            by_source[term["source"]] = term
    return compact_glossary_terms(list(by_source.values()))


def import_glossary_csv(text: str, default_status: str = "pending") -> list[dict]:
    stream = io.StringIO(text)
    reader = csv.DictReader(stream)
    rows: list[dict] = []
    for row in reader:
        if not row:
            continue
        rows.append(_row_from_mapping(row, default_status=default_status))
    return compact_glossary_terms(rows)


def export_glossary_csv(terms: list[dict]) -> str:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=GLOSSARY_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for term in compact_glossary_terms(terms):
        writer.writerow(_row_to_mapping(term))
    return stream.getvalue()


def import_glossary_tbx(text: str, default_status: str = "pending") -> list[dict]:
    root = ET.fromstring(text)
    rows: list[dict] = []
    for entry in root.iter():
        if _local(entry.tag) != "termEntry":
            continue
        term_type = _entry_note(entry, "type") or "special"
        status = _entry_note(entry, "status") or default_status
        locked = _bool(_entry_note(entry, "locked"))
        confidence = _float(_entry_note(entry, "confidence"), 1.0 if locked or status == "approved" else 0.0)
        aliases = _entry_note(entry, "aliases")
        language_terms: list[tuple[str, str]] = []
        for lang_set in entry:
            if _local(lang_set.tag) != "langSet":
                continue
            lang = lang_set.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") or lang_set.attrib.get("lang") or ""
            terms = [_node_text(node) for node in lang_set.iter() if _local(node.tag) == "term"]
            if not terms:
                continue
            language_terms.append((lang, terms[0]))
        source = language_terms[0][1] if language_terms else ""
        translation = language_terms[1][1] if len(language_terms) > 1 else ""
        if source or translation:
            rows.append(
                {
                    "source": source,
                    "translation": translation,
                    "type": term_type,
                    "aliases": aliases or "",
                    "status": status,
                    "confidence": confidence,
                    "locked": locked,
                }
            )
    return compact_glossary_terms(rows)


def export_glossary_tbx(terms: list[dict], target_language: str = "Simplified Chinese") -> str:
    root = ET.Element("tbx", {"style": "dca"})
    body = ET.SubElement(ET.SubElement(root, "text"), "body")
    target_lang = _target_language_code(target_language)
    for index, raw in enumerate(compact_glossary_terms(terms), start=1):
        term = normalize_glossary_term(raw)
        entry = ET.SubElement(body, "termEntry", {"id": f"term-{index}"})
        for key in ("type", "status", "confidence", "locked"):
            note = ET.SubElement(entry, "descrip", {"type": key})
            note.text = str(term.get(key, ""))
        if term.get("aliases"):
            note = ET.SubElement(entry, "descrip", {"type": "aliases"})
            note.text = ", ".join(term["aliases"])
        source_lang = ET.SubElement(entry, "langSet", {"{http://www.w3.org/XML/1998/namespace}lang": "source"})
        source_tig = ET.SubElement(source_lang, "tig")
        ET.SubElement(source_tig, "term").text = term["source"]
        target_lang_set = ET.SubElement(entry, "langSet", {"{http://www.w3.org/XML/1998/namespace}lang": target_lang})
        target_tig = ET.SubElement(target_lang_set, "tig")
        ET.SubElement(target_tig, "term").text = term.get("translation", "")
    return ET.tostring(root, encoding="unicode") + "\n"


def import_glossary_markdown(text: str, default_status: str = "pending") -> list[dict]:
    rows: list[dict] = []
    in_table = False
    headers: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells):
                continue
            lowered = [_header_name(cell) for cell in cells]
            if "source" in lowered and ("translation" in lowered or "target" in lowered):
                headers = lowered
                in_table = True
                continue
            if in_table and headers:
                mapping = {headers[index]: cells[index] if index < len(cells) else "" for index in range(len(headers))}
                rows.append(_row_from_mapping(mapping, default_status=default_status))
                continue
        bullet = re.match(r"^[-*]\s*(?P<source>.+?)(?:\s*->\s*(?P<translation>.*?))?(?:\s*\((?P<meta>[^)]*)\))?$", line)
        if bullet:
            source = bullet.group("source").strip()
            translation = (bullet.group("translation") or "").strip()
            meta = bullet.group("meta") or ""
            if source and source.lower() != "no pending candidates.":
                rows.append(_term_from_markdown_parts(source, translation, meta, default_status))
    return compact_glossary_terms(rows)


def export_glossary_markdown(terms: list[dict], target_language: str = "Simplified Chinese") -> str:
    rows = [
        "# Babel Glossary Preset",
        "",
        f"Target language: {target_language}",
        "",
        "| Source | Translation | Type | Aliases | Status | Confidence | Locked |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for term in compact_glossary_terms(terms):
        rows.append(
            "| {source} | {translation} | {type} | {aliases} | {status} | {confidence:.2f} | {locked} |".format(
                source=term["source"],
                translation=term.get("translation", ""),
                type=term.get("type", "special"),
                aliases=", ".join(term.get("aliases", [])),
                status=term.get("status", "pending"),
                confidence=float(term.get("confidence", 0.0) or 0.0),
                locked="true" if term.get("locked") else "false",
            )
        )
    return "\n".join(rows) + "\n"


def _with_default_status(row: dict, default_status: str) -> dict:
    item = dict(row)
    item.setdefault("status", default_status)
    return item


def _row_from_mapping(row: dict, default_status: str = "pending") -> dict:
    normalized = {str(key or "").strip().lower().replace(" ", "_"): value for key, value in row.items()}
    aliases = normalized.get("aliases", "")
    evidence = normalized.get("evidence", "")
    return {
        "source": normalized.get("source") or normalized.get("term") or normalized.get("source_term") or "",
        "translation": normalized.get("translation") or normalized.get("target") or normalized.get("target_term") or "",
        "type": normalized.get("type") or normalized.get("term_type") or "special",
        "aliases": _split_list(aliases),
        "frequency": _int(normalized.get("frequency"), 0),
        "evidence": _split_list(evidence)[:3],
        "status": normalized.get("status") or default_status,
        "confidence": _float(normalized.get("confidence"), 0.0),
        "locked": _bool(normalized.get("locked")),
    }


def _row_to_mapping(term: dict) -> dict:
    item = normalize_glossary_term(term)
    return {
        "source": item["source"],
        "translation": item.get("translation", ""),
        "type": item.get("type", "special"),
        "aliases": "; ".join(item.get("aliases", [])),
        "frequency": str(item.get("frequency", 0)),
        "evidence": " | ".join(item.get("evidence", [])),
        "status": item.get("status", "pending"),
        "confidence": f"{float(item.get('confidence', 0.0) or 0.0):.2f}",
        "locked": "true" if item.get("locked") else "false",
    }


def _term_from_markdown_parts(source: str, translation: str, meta: str, default_status: str) -> dict:
    frequency = 0
    term_type = "special"
    confidence = 0.0
    parts = [part.strip() for part in meta.split(",") if part.strip()]
    if parts:
        frequency = _int(parts[0], 0)
    if len(parts) > 1:
        term_type = parts[1]
    for part in parts:
        match = re.search(r"confidence\s+([0-9.]+)", part, flags=re.IGNORECASE)
        if match:
            confidence = _float(match.group(1), 0.0)
    status = "approved" if translation and confidence >= 0.9 else default_status
    return {
        "source": source,
        "translation": translation,
        "type": term_type,
        "frequency": frequency,
        "status": status,
        "confidence": confidence,
        "locked": status == "approved",
    }


def _header_name(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    aliases = {
        "source_term": "source",
        "target": "translation",
        "target_term": "translation",
        "notes": "note",
    }
    return aliases.get(lowered, lowered)


def _entry_note(entry: ET.Element, note_type: str) -> str:
    for node in entry:
        if _local(node.tag) in {"descrip", "note"} and node.attrib.get("type") == note_type:
            return _node_text(node)
    return ""


def _node_text(node: ET.Element) -> str:
    return "".join(node.itertext()).strip()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if tag.startswith("{") else tag


def _split_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in re.split(r"[;|,]", str(value or "")) if part.strip()]


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "locked", "approved"}


def _int(value: object, default: int) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _float(value: object, default: float) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _target_language_code(target_language: str) -> str:
    lowered = target_language.lower()
    if "chinese" in lowered or "zh" in lowered or "中文" in target_language:
        return "zh-CN"
    if "japanese" in lowered:
        return "ja"
    if "english" in lowered:
        return "en"
    return target_language or "target"
