"""Structured glossary extraction and quality checks for Babel jobs."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from xml.etree import ElementTree as ET


GLOSSARY_TERMS_FILE = "glossary_terms.json"
AI_QUALITY_REPORT_FILE = "ai_quality_report.json"

NAME_RE = re.compile(r"\b[A-Z][A-Za-z’'’-]+(?:\s+[A-Z][A-Za-z’'’-]+){0,3}\b")
LOWER_TERM_RE = re.compile(r"\b[a-z][a-z]{4,}(?:-[a-z]{3,})?\b")
HTML_TAG_RE = re.compile(r"<[^>]+>")

COMMON_FALSE_POSITIVES = {
    "A",
    "About",
    "Above",
    "Across",
    "Actually",
    "After",
    "Again",
    "Ahead",
    "All",
    "Although",
    "Always",
    "And",
    "Another",
    "Any",
    "Anyway",
    "Are",
    "As",
    "At",
    "Back",
    "Before",
    "Behind",
    "Below",
    "Beside",
    "Both",
    "But",
    "By",
    "Can",
    "Careful",
    "Chapter",
    "Come",
    "Could",
    "Did",
    "Do",
    "Don",
    "Even",
    "Every",
    "Everything",
    "Farewell",
    "Finally",
    "First",
    "Follow",
    "For",
    "Get",
    "Go",
    "Good",
    "Goodbye",
    "Got",
    "Had",
    "Have",
    "Having",
    "He",
    "Her",
    "Here",
    "Hold",
    "How",
    "His",
    "If",
    "In",
    "Indeed",
    "Instead",
    "Is",
    "It",
    "I'm",
    "I’m",
    "Just",
    "Keep",
    "Let",
    "Like",
    "Look",
    "Make",
    "Many",
    "May",
    "Meanwhile",
    "Most",
    "My",
    "Never",
    "Next",
    "Night",
    "No",
    "None",
    "Nothing",
    "Now",
    "Oh",
    "One",
    "Only",
    "Our",
    "Out",
    "Over",
    "Perhaps",
    "Please",
    "Quick",
    "Remember",
    "See",
    "She",
    "Since",
    "Sir",
    "Some",
    "Something",
    "Soon",
    "Still",
    "Such",
    "Suddenly",
    "Sure",
    "Surely",
    "Take",
    "Thank",
    "Thanks",
    "That",
    "The",
    "Their",
    "There",
    "They",
    "This",
    "Those",
    "Though",
    "Three",
    "Through",
    "To",
    "Today",
    "Together",
    "Tonight",
    "Too",
    "Two",
    "Unlike",
    "Up",
    "Very",
    "Wait",
    "Was",
    "We",
    "Well",
    "What",
    "When",
    "Who",
    "While",
    "Why",
    "With",
    "Without",
    "Would",
    "Yes",
    "Yet",
    "You",
    "Your",
}
COMMON_FALSE_POSITIVES_LOWER = {item.lower() for item in COMMON_FALSE_POSITIVES}

LOWER_FALSE_POSITIVES = {
    "chapter",
    "class",
    "content",
    "ebook",
    "epub",
    "href",
    "image",
    "images",
    "indent",
    "nonindent",
    "padding",
    "paragraph",
    "source",
    "style",
    "translation",
}

KNOWN_TRANSLATIONS = {
    "Alquix": "阿尔奎克斯",
    "Alquix Venvax": "阿尔奎克斯·文瓦克斯",
    "Banderbear": "班德熊",
    "Banderbears": "班德熊",
    "banderbear": "班德熊",
    "banderbears": "班德熊",
    "Barkwater": "巴克沃特",
    "Captain Twig": "特威格船长",
    "Deepwoods": "深林",
    "Felix": "费利克斯",
    "Felix Lodd": "费利克斯·洛德",
    "Free Glades": "自由林地",
    "Great Mire Road": "大沼泽路",
    "Great Storm Chamber": "大风暴室",
    "Great Storm Chamber Library": "大风暴室图书馆",
    "Guardians of Night": "夜之守护者",
    "Hekkle": "赫克尔",
    "High Academe": "至高学阀",
    "Lake Landing": "湖岸",
    "Lufwood Bridge": "卢夫木桥",
    "Lodd": "洛德",
    "Magda": "玛格达",
    "Magda Burlix": "玛格达·伯利克斯",
    "Most High Academe": "至高学阀",
    "Rook": "鲁克",
    "Rook Barkwater": "鲁克·巴克沃特",
    "Sanctaphrax": "圣弗拉克斯",
    "Skyraider": "天空劫掠者",
    "Stob": "斯托布",
    "Stob Lummus": "斯托布·拉穆斯",
    "Stormhornet": "风暴蜂",
    "Twig": "特威格",
    "Undertown": "下城镇",
    "Vox Verlix": "沃克斯·维尔利克斯",
    "Varis": "瓦里斯",
    "Varis Lodd": "瓦里斯·洛德",
    "Xanth": "赞斯",
}

KNOWN_SOURCE_TERMS = tuple(
    sorted(
        (term for term in KNOWN_TRANSLATIONS if any(part[:1].islower() for part in term.split())),
        key=lambda item: (-len(item.split()), -len(item)),
    )
)

TITLE_WORDS = {
    "Academe",
    "Captain",
    "Guardian",
    "Guardians",
    "High",
    "Knight",
    "Librarian",
    "Master",
    "Mistress",
    "Professor",
}
PLACE_WORDS = {
    "Bridge",
    "Chamber",
    "Deepwoods",
    "Edge",
    "Edgelands",
    "Gate",
    "Glade",
    "Glades",
    "Landing",
    "Library",
    "Market",
    "Mire",
    "Road",
    "Sanctaphrax",
    "Tower",
    "Town",
    "Undertown",
    "Valley",
    "Woods",
}
ORG_WORDS = {"Academe", "Academics", "Guardians", "Library", "Nations", "Sisterhood"}
CREATURE_WORDS = {
    "banderbear",
    "banderbears",
    "cowlquape",
    "gobrat",
    "hammelhorn",
    "lugtroll",
    "prowlgrin",
    "shryke",
    "shrykes",
    "stormhornet",
    "vulpoon",
    "woodhog",
    "woodmoth",
}


@dataclass
class GlossaryTerm:
    source: str
    translation: str = ""
    type: str = "special"
    aliases: list[str] = field(default_factory=list)
    frequency: int = 0
    evidence: list[str] = field(default_factory=list)
    status: str = "pending"
    confidence: float = 0.0
    locked: bool = False

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "translation": self.translation,
            "type": self.type,
            "aliases": self.aliases,
            "frequency": self.frequency,
            "evidence": self.evidence,
            "status": self.status,
            "confidence": self.confidence,
            "locked": self.locked,
        }


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_term(value: str) -> str:
    term = re.sub(r"\s+", " ", value.replace("’", "'")).strip(" \t\r\n.,;:!?()[]{}\"“”")
    term = re.sub(r"'s$", "", term)
    return term.replace("'", "’")


def html_text(value: str) -> str:
    try:
        element = ET.fromstring(value)
        return "".join(element.itertext())
    except ET.ParseError:
        return unescape(HTML_TAG_RE.sub("", value))


def clean_evidence(value: str, term: str = "", limit: int = 160) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if term:
        match = re.search(re.escape(term), compact, flags=re.IGNORECASE)
        if match:
            start = max(match.start() - 60, 0)
            end = min(match.end() + 90, len(compact))
            snippet = compact[start:end]
            prefix = "..." if start else ""
            suffix = "..." if end < len(compact) else ""
            return f"{prefix}{snippet}{suffix}"
    return compact[:limit]


def classify_term(term: str) -> str:
    lowered = term.lower()
    parts = term.split()
    if lowered in CREATURE_WORDS or any(part.lower() in CREATURE_WORDS for part in parts):
        return "creature"
    if any(part in TITLE_WORDS for part in parts):
        return "title"
    if any(part in ORG_WORDS for part in parts) and len(parts) > 1:
        return "organization"
    if any(part in PLACE_WORDS for part in parts):
        return "place"
    if len(parts) >= 2 and all(part[:1].isupper() for part in parts):
        return "person"
    if term[:1].isupper():
        return "person"
    return "special"


def term_confidence(term: str, term_type: str, frequency: int) -> float:
    if term in KNOWN_TRANSLATIONS:
        return 0.95
    if term_type in {"place", "organization", "title"} and len(term.split()) > 1 and frequency >= 5:
        return 0.74
    if term_type == "creature" and frequency >= 3:
        return 0.7
    if term_type == "person" and len(term.split()) > 1 and frequency >= 3:
        return 0.68
    if term_type in {"person", "place"}:
        return 0.58
    return 0.45


def suggest_translation(term: str, term_type: str) -> str:
    del term_type
    if term in KNOWN_TRANSLATIONS:
        return KNOWN_TRANSLATIONS[term]
    # Keep unknown terms reviewable instead of creating bad automatic hard constraints.
    return ""


def collect_term_counts(blocks: list[dict]) -> tuple[Counter[str], dict[str, list[str]]]:
    counts: Counter[str] = Counter()
    evidence: dict[str, list[str]] = defaultdict(list)
    for block in blocks:
        text = str(block.get("source_text", ""))
        for known in KNOWN_SOURCE_TERMS:
            if contains_term(text, known):
                counts[known] += 1
                if len(evidence[known]) < 3:
                    evidence[known].append(clean_evidence(text, known))
        for match in NAME_RE.findall(text):
            term = normalize_term(match)
            if should_skip_name_candidate(term):
                continue
            if all(part in COMMON_FALSE_POSITIVES for part in term.split()):
                continue
            counts[term] += 1
            if len(evidence[term]) < 3:
                evidence[term].append(clean_evidence(text, term))
        for match in LOWER_TERM_RE.findall(text):
            term = normalize_term(match.lower())
            if term in LOWER_FALSE_POSITIVES or term not in CREATURE_WORDS:
                continue
            counts[term] += 1
            if len(evidence[term]) < 3:
                evidence[term].append(clean_evidence(text, term))
    return counts, evidence


def should_skip_name_candidate(term: str) -> bool:
    if not term:
        return True
    if term in KNOWN_TRANSLATIONS:
        return False
    normalized = normalize_term(term)
    parts = normalized.split()
    lowered = normalized.lower()
    if normalized in COMMON_FALSE_POSITIVES or lowered in COMMON_FALSE_POSITIVES_LOWER:
        return True
    if "’" in normalized or "'" in normalized:
        return True
    if len(parts) == 1 and lowered in {"madam", "master", "mistress", "night", "sir", "unlike"}:
        return True
    if len(parts) == 1 and len(normalized) <= 2:
        return True
    return False


def build_glossary_terms(pipeline_dir: Path, target_language: str = "Simplified Chinese") -> list[dict]:
    del target_language
    blocks = read_jsonl(pipeline_dir / "blocks.jsonl")
    counts, evidence = collect_term_counts(blocks)
    terms: list[GlossaryTerm] = []
    for source, frequency in counts.most_common():
        if frequency < 2 and source not in KNOWN_TRANSLATIONS:
            continue
        term_type = classify_term(source)
        confidence = term_confidence(source, term_type, frequency)
        translation = suggest_translation(source, term_type)
        status = "approved" if confidence >= 0.9 and translation else "pending"
        terms.append(
            GlossaryTerm(
                source=source,
                translation=translation,
                type=term_type,
                aliases=aliases_for(source, counts),
                frequency=frequency,
                evidence=evidence.get(source, []),
                status=status,
                confidence=round(confidence, 2),
                locked=status == "approved",
            )
        )
    payload = compact_glossary_terms([term.to_dict() for term in terms[:240]])
    write_json(pipeline_dir / GLOSSARY_TERMS_FILE, payload)
    return payload


def aliases_for(source: str, counts: Counter[str]) -> list[str]:
    aliases: list[str] = []
    possessive = f"{source}’s"
    if possessive in counts:
        aliases.append(possessive)
    words = source.split()
    if len(words) > 1 and words[0] in counts:
        aliases.append(words[0])
    return aliases[:4]


def glossary_terms_path(work_dir: Path) -> Path:
    return work_dir / "pipeline" / GLOSSARY_TERMS_FILE


def read_glossary_terms(work_dir: Path) -> list[dict]:
    path = glossary_terms_path(work_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return compact_glossary_terms(payload)


def write_glossary_terms(work_dir: Path, terms: list[dict]) -> list[dict]:
    normalized = compact_glossary_terms(terms)
    write_json(glossary_terms_path(work_dir), normalized)
    return normalized


def compact_glossary_terms(terms: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    seen: set[str] = set()
    for term in terms:
        if not isinstance(term, dict):
            continue
        item = normalize_glossary_term(term)
        source = item["source"]
        if not source or should_skip_name_candidate(source):
            continue
        if source in seen:
            continue
        seen.add(source)
        normalized.append(item)
    return normalized


def normalize_glossary_term(term: dict) -> dict:
    source = normalize_term(str(term.get("source", "")))
    aliases = term.get("aliases", [])
    if isinstance(aliases, str):
        aliases = [part.strip() for part in aliases.split(",") if part.strip()]
    if not isinstance(aliases, list):
        aliases = []
    return {
        "source": source,
        "translation": str(term.get("translation", "")).strip(),
        "type": str(term.get("type", "special") or "special"),
        "aliases": [normalize_term(str(alias)) for alias in aliases if str(alias).strip()],
        "frequency": int(term.get("frequency", 0) or 0),
        "evidence": list(term.get("evidence", []) or [])[:3],
        "status": str(term.get("status", "pending") or "pending"),
        "confidence": float(term.get("confidence", 0.0) or 0.0),
        "locked": bool(term.get("locked", False)),
    }


def enforced_terms(terms: list[dict]) -> list[dict]:
    result = []
    for term in terms:
        source = str(term.get("source", "")).strip()
        translation = str(term.get("translation", "")).strip()
        status = str(term.get("status", ""))
        confidence = float(term.get("confidence", 0.0) or 0.0)
        if not source or not translation or status == "ignored" or should_skip_name_candidate(source):
            continue
        if status == "approved" or bool(term.get("locked")) or confidence >= 0.9:
            result.append(normalize_glossary_term(term))
    return result


def render_glossary_markdown(target_language: str, terms: list[dict]) -> str:
    enforced = enforced_terms(terms)
    pending = [normalize_glossary_term(term) for term in terms if term.get("status") == "pending"][:80]
    decision_rows = [
        "| Source | Translation | Type | Aliases | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    if enforced:
        for term in enforced:
            aliases = ", ".join(term.get("aliases", []))
            decision_rows.append(
                f"| {term['source']} | {term['translation']} | {term['type']} | {aliases} | locked |"
            )
    else:
        decision_rows.append("| TODO | TODO | term |  | Add confirmed decisions before dispatching batches. |")

    candidate_lines = []
    for term in pending:
        draft = f" -> {term['translation']}" if term.get("translation") else ""
        candidate_lines.append(
            f"- {term['source']}{draft} "
            f"({term['frequency']}, {term['type']}, confidence {term['confidence']:.2f})"
        )
    if not candidate_lines:
        candidate_lines = ["- No pending candidates."]
    return (
        "# Translation Glossary\n\n"
        "This glossary is generated from structured `glossary_terms.json` and is the compact prompt surface for workers.\n\n"
        "## Global Style\n\n"
        f"- Target language: {target_language}.\n"
        "- Translate naturally and contextually. Do not translate sentence-by-sentence mechanically.\n"
        "- Preserve source tone, pacing, paragraph structure, humor, implication, register, and emotional continuity.\n"
        "- Translate only human-readable text while preserving XHTML tags and structural attributes.\n"
        "- Apply every locked term consistently. Do not leave locked source terms untranslated unless the source intentionally quotes them as foreign text.\n\n"
        "## Locked Name And Term Decisions\n\n"
        + "\n".join(decision_rows)
        + "\n\n## Pending Candidates\n\n"
        + "\n".join(candidate_lines)
        + "\n"
    )


def glossary_summary(terms: list[dict]) -> dict:
    total = len(terms)
    approved = len([term for term in terms if term.get("status") == "approved" or term.get("locked")])
    pending = len([term for term in terms if term.get("status") == "pending"])
    ignored = len([term for term in terms if term.get("status") == "ignored"])
    return {"total": total, "approved": approved, "pending": pending, "ignored": ignored}


def batch_number_from_output(path: str) -> int:
    match = re.search(r"batch_(\d+)_", path)
    return int(match.group(1)) if match else 0


def detect_glossary_issues(pipeline_dir: Path, terms: list[dict]) -> list[dict]:
    enforced = enforced_terms(terms)
    if not enforced:
        return []
    manifest_path = pipeline_dir / "batch_manifest.json"
    if not manifest_path.exists():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    issues: list[dict] = []
    for batch in manifest:
        batch_rows = {row["id"]: row for row in read_jsonl(pipeline_dir / batch["input"])}
        translated_path = pipeline_dir / batch["output"]
        if not translated_path.exists():
            continue
        for translated in read_jsonl(translated_path):
            row_id = translated.get("id", "")
            source_row = batch_rows.get(row_id, {})
            source_text = str(source_row.get("source_text", ""))
            translated_html = str(translated.get("translated_html", ""))
            translated_text = html_text(translated_html)
            for term in enforced:
                source = term["source"]
                aliases = [source, *term.get("aliases", [])]
                if not any(contains_term(source_text, alias) for alias in aliases):
                    continue
                if any(contains_term(translated_text, alias) for alias in aliases):
                    issues.append(
                        {
                            "batch": batch.get("batch"),
                            "row_id": row_id,
                            "source": source,
                            "translation": term["translation"],
                            "kind": "untranslated-source-term",
                            "message": f"{source} remains untranslated",
                        }
                    )
                elif term["translation"] and term["translation"] not in translated_text:
                    issues.append(
                        {
                            "batch": batch.get("batch"),
                            "row_id": row_id,
                            "source": source,
                            "translation": term["translation"],
                            "kind": "missing-locked-translation",
                            "message": f"{source} does not use locked translation {term['translation']}",
                        }
                    )
    return issues


def contains_term(text: str, term: str) -> bool:
    if not term:
        return False
    if re.search(r"[A-Za-z]", term):
        return re.search(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])", text) is not None
    return term in text


def repair_untranslated_terms(pipeline_dir: Path, terms: list[dict], issues: list[dict]) -> int:
    if not issues:
        return 0
    rows_by_id = {issue["row_id"] for issue in issues if issue.get("kind") == "untranslated-source-term"}
    if not rows_by_id:
        return 0
    enforced = enforced_terms(terms)
    repaired = 0
    manifest = json.loads((pipeline_dir / "batch_manifest.json").read_text(encoding="utf-8"))
    for batch in manifest:
        translated_path = pipeline_dir / batch["output"]
        if not translated_path.exists():
            continue
        changed = False
        translated_rows = read_jsonl(translated_path)
        for row in translated_rows:
            if row.get("id") not in rows_by_id:
                continue
            html = str(row.get("translated_html", ""))
            new_html = html
            for term in enforced:
                for alias in [term["source"], *term.get("aliases", [])]:
                    if alias:
                        new_html = replace_source_term(new_html, alias, term["translation"])
            if new_html != html:
                row["translated_html"] = new_html
                repaired += 1
                changed = True
        if changed:
            translated_path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in translated_rows),
                encoding="utf-8",
            )
    return repaired


def replace_source_term(value: str, source: str, translation: str) -> str:
    if not source or not translation:
        return value
    if re.search(r"[A-Za-z]", source):
        return re.sub(r"(?<![A-Za-z])" + re.escape(source) + r"(?![A-Za-z])", translation, value)
    return value.replace(source, translation)


def write_ai_quality_report(pipeline_dir: Path, report: dict) -> Path:
    path = pipeline_dir / AI_QUALITY_REPORT_FILE
    write_json(path, report)
    return path
