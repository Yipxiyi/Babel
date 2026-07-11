"""Structured glossary extraction and quality checks for Babel jobs."""

from __future__ import annotations

import json
import re
from importlib import resources
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
    "An",
    "Another",
    "Any",
    "Anyway",
    "Apart",
    "Are",
    "Around",
    "As",
    "At",
    "Aye",
    "Back",
    "Before",
    "Behind",
    "Below",
    "Beneath",
    "Because",
    "Believe",
    "Beside",
    "Both",
    "But",
    "By",
    "Can",
    "Careful",
    "Chapter",
    "Christ",
    "Coach",
    "Come",
    "Could",
    "Crap",
    "Dad",
    "Damn",
    "Darkness",
    "Dead",
    "Delicious",
    "Did",
    "Despite",
    "Do",
    "Don",
    "Down",
    "Dude",
    "Each",
    "Earth",
    "Even",
    "Ever",
    "Every",
    "Everything",
    "Except",
    "Fare",
    "Farewell",
    "Finally",
    "Fine",
    "First",
    "Fifty",
    "Flying",
    "Follow",
    "For",
    "Friday",
    "From",
    "Far",
    "Fuck",
    "Get",
    "Go",
    "Good",
    "Goodbye",
    "Got",
    "God",
    "Great",
    "Had",
    "Have",
    "Having",
    "He",
    "Heart",
    "Her",
    "Here",
    "Hell",
    "Help",
    "Hey",
    "Hold",
    "Holy",
    "How",
    "His",
    "If",
    "In",
    "Indeed",
    "Instead",
    "Into",
    "Is",
    "It",
    "Its",
    "I'm",
    "I’m",
    "Jesus",
    "Just",
    "Keep",
    "Leave",
    "Let",
    "Like",
    "Light",
    "Look",
    "Looking",
    "Loom",
    "Make",
    "Many",
    "May",
    "Maybe",
    "Meanwhile",
    "Mom",
    "More",
    "Most",
    "My",
    "Naah",
    "Never",
    "Next",
    "Night",
    "No",
    "No-one",
    "Nope",
    "None",
    "Nor",
    "Not",
    "Nothing",
    "Now",
    "Oh",
    "Of",
    "Off",
    "Okay",
    "On",
    "One",
    "Only",
    "Once",
    "Open",
    "Our",
    "Out",
    "Over",
    "Pass",
    "Perhaps",
    "Please",
    "Professors",
    "Quick",
    "Quickly",
    "Remember",
    "Really",
    "Right",
    "See",
    "Seriously",
    "Several",
    "She",
    "Shit",
    "Since",
    "Sir",
    "Slowly",
    "Some",
    "Someone",
    "Something",
    "Sometimes",
    "Soon",
    "Sorry",
    "Still",
    "Stay",
    "Steady",
    "Stop",
    "Study",
    "Such",
    "Suddenly",
    "Sure",
    "Surely",
    "T-shirt",
    "Take",
    "Thank",
    "Thanks",
    "That",
    "The",
    "Their",
    "Then",
    "There",
    "They",
    "This",
    "Those",
    "Though",
    "Three",
    "Through",
    "To",
    "Time",
    "Today",
    "Together",
    "Tonight",
    "Too",
    "Trust",
    "Twitter",
    "Two",
    "Uh-huh",
    "Unlike",
    "Unless",
    "Up",
    "Very",
    "Wait",
    "Wahoo",
    "Was",
    "We",
    "Welcome",
    "Well",
    "What",
    "When",
    "Where",
    "Who",
    "While",
    "Why",
    "Which",
    "With",
    "Without",
    "Would",
    "Yeah",
    "Yes",
    "Yet",
    "Yep",
    "Yup",
    "You",
    "Your",
    "Aargh",
    "Urrgh",
    "Whup",
    "Wuh",
    "Wuh-wuh",
}
COMMON_FALSE_POSITIVES_LOWER = {item.lower() for item in COMMON_FALSE_POSITIVES}
LEADING_FALSE_POSITIVES_LOWER = {
    "a",
    "although",
    "an",
    "and",
    "as",
    "at",
    "because",
    "but",
    "by",
    "despite",
    "each",
    "except",
    "for",
    "from",
    "if",
    "in",
    "into",
    "of",
    "off",
    "on",
    "since",
    "the",
    "then",
    "though",
    "through",
    "to",
    "unless",
    "when",
    "where",
    "while",
    "with",
    "without",
}

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



@dataclass(frozen=True)
class GlossaryPreset:
    translations: dict[str, str] = field(default_factory=dict)
    title_words: frozenset[str] = frozenset()
    place_words: frozenset[str] = frozenset()
    org_words: frozenset[str] = frozenset()
    creature_words: frozenset[str] = frozenset()

    @property
    def known_source_terms(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                (
                    term
                    for term in self.translations
                    if any(part[:1].islower() for part in term.split())
                ),
                key=lambda item: (-len(item.split()), -len(item)),
            )
        )


EMPTY_GLOSSARY_PRESET = GlossaryPreset()


def _preset_from_payload(payload: dict) -> GlossaryPreset:
    translations = payload.get("translations", {})
    if not isinstance(translations, dict):
        translations = {}
    return GlossaryPreset(
        translations={str(key): str(value) for key, value in translations.items()},
        title_words=frozenset(str(value) for value in payload.get("title_words", []) if str(value).strip()),
        place_words=frozenset(str(value) for value in payload.get("place_words", []) if str(value).strip()),
        org_words=frozenset(str(value) for value in payload.get("org_words", []) if str(value).strip()),
        creature_words=frozenset(str(value).lower() for value in payload.get("creature_words", []) if str(value).strip()),
    )


def load_glossary_preset(preset: str | Path | None = None) -> GlossaryPreset:
    if not preset:
        return EMPTY_GLOSSARY_PRESET
    value = str(preset).strip()
    if not value:
        return EMPTY_GLOSSARY_PRESET
    path = Path(value).expanduser()
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"glossary preset must be a JSON object: {path}")
        return _preset_from_payload(payload)
    filename = value if value.endswith(".json") else f"{value}.json"
    try:
        resource = resources.files("babel_epub.presets").joinpath(filename)
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"unknown glossary preset: {value}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"glossary preset must be a JSON object: {value}")
    return _preset_from_payload(payload)


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


def classify_term(term: str, preset: GlossaryPreset = EMPTY_GLOSSARY_PRESET) -> str:
    lowered = term.lower()
    parts = term.split()
    if lowered in preset.creature_words or any(part.lower() in preset.creature_words for part in parts):
        return "creature"
    if any(part in preset.title_words for part in parts):
        return "title"
    if any(part in preset.org_words for part in parts) and len(parts) > 1:
        return "organization"
    if any(part in preset.place_words for part in parts):
        return "place"
    if len(parts) >= 2 and all(part[:1].isupper() for part in parts):
        return "person"
    if term[:1].isupper():
        return "person"
    return "special"


def term_confidence(term: str, term_type: str, frequency: int, preset: GlossaryPreset = EMPTY_GLOSSARY_PRESET) -> float:
    if term in preset.translations:
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


def suggest_translation(term: str, term_type: str, preset: GlossaryPreset = EMPTY_GLOSSARY_PRESET) -> str:
    del term_type
    if term in preset.translations:
        return preset.translations[term]
    # Keep unknown terms reviewable instead of creating bad automatic hard constraints.
    return ""


def collect_term_counts(blocks: list[dict], preset: GlossaryPreset = EMPTY_GLOSSARY_PRESET) -> tuple[Counter[str], dict[str, list[str]]]:
    counts: Counter[str] = Counter()
    evidence: dict[str, list[str]] = defaultdict(list)
    for block in blocks:
        text = str(block.get("source_text", ""))
        for known in preset.known_source_terms:
            if contains_term(text, known):
                counts[known] += 1
                if len(evidence[known]) < 3:
                    evidence[known].append(clean_evidence(text, known))
        for match in NAME_RE.findall(text):
            term = normalize_term(match)
            if should_skip_name_candidate(term, preset.translations):
                continue
            if all(part in COMMON_FALSE_POSITIVES for part in term.split()):
                continue
            counts[term] += 1
            if len(evidence[term]) < 3:
                evidence[term].append(clean_evidence(text, term))
        for match in LOWER_TERM_RE.findall(text):
            term = normalize_term(match.lower())
            if term in LOWER_FALSE_POSITIVES or term not in preset.creature_words:
                continue
            counts[term] += 1
            if len(evidence[term]) < 3:
                evidence[term].append(clean_evidence(text, term))
    return counts, evidence


def should_skip_name_candidate(term: str, known_translations: dict[str, str] | None = None) -> bool:
    if not term:
        return True
    if known_translations and term in known_translations:
        return False
    normalized = normalize_term(term)
    parts = normalized.split()
    lowered = normalized.lower()
    if normalized in COMMON_FALSE_POSITIVES or lowered in COMMON_FALSE_POSITIVES_LOWER:
        return True
    lowered_parts = [part.lower() for part in parts]
    if parts and all(part in COMMON_FALSE_POSITIVES_LOWER for part in lowered_parts):
        return True
    if len(parts) > 1 and lowered_parts[0] in LEADING_FALSE_POSITIVES_LOWER:
        return True
    if "’" in normalized or "'" in normalized:
        return True
    if len(parts) == 1 and lowered in {"madam", "master", "mistress", "night", "sir", "unlike"}:
        return True
    if len(parts) == 1 and len(normalized) <= 2:
        return True
    return False


def build_glossary_terms(
    pipeline_dir: Path,
    target_language: str = "Simplified Chinese",
    glossary_preset: str | Path | None = None,
) -> list[dict]:
    del target_language
    preset = load_glossary_preset(glossary_preset)
    blocks = read_jsonl(pipeline_dir / "blocks.jsonl")
    counts, evidence = collect_term_counts(blocks, preset)
    terms: list[GlossaryTerm] = []
    for source, frequency in counts.most_common():
        if frequency < 2 and source not in preset.translations:
            continue
        term_type = classify_term(source, preset)
        confidence = term_confidence(source, term_type, frequency, preset)
        translation = suggest_translation(source, term_type, preset)
        status = "approved" if confidence >= 0.9 and translation else "pending"
        terms.append(
            GlossaryTerm(
                source=source,
                translation=translation,
                type=term_type,
                aliases=aliases_for(source, counts, preset),
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


def aliases_for(source: str, counts: Counter[str], preset: GlossaryPreset = EMPTY_GLOSSARY_PRESET) -> list[str]:
    aliases: list[str] = []
    possessive = f"{source}’s"
    if possessive in counts:
        aliases.append(possessive)
    words = source.split()
    if (
        len(words) > 1
        and classify_term(source, preset) == "person"
        and words[0] in counts
        and not should_skip_name_candidate(words[0], preset.translations)
    ):
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



LONG_UNTRANSLATED_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’,-]*(?:\s+[A-Za-z][A-Za-z0-9'’,-]*){4,}")
SOURCE_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’.-]{3,}")
QUOTE_CHARS = '"“”‘’«»‹›「」『』'
SENTENCE_PUNCTUATION = ".!?。！？"


def detect_deterministic_quality(pipeline_dir: Path, terms: list[dict]) -> dict:
    manifest_path = pipeline_dir / "batch_manifest.json"
    if not manifest_path.exists():
        return _empty_quality_report()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_quality_report()

    person_terms = [term for term in compact_glossary_terms(terms) if term.get("type") == "person"]
    issues: list[dict] = []
    long_segments: list[dict] = []
    punctuation_drift: list[dict] = []
    person_name_drift: list[dict] = []
    chapter_counts: dict[str, dict] = defaultdict(lambda: {"rows": 0, "issues": 0, "blocking": 0, "nonblocking": 0})
    row_count = 0
    source_char_count = 0
    unchanged_source_chars = 0

    for batch in manifest:
        batch_rows = {row.get("id", ""): row for row in read_jsonl(pipeline_dir / batch.get("input", ""))}
        translated_path = pipeline_dir / batch.get("output", "")
        if not translated_path.exists():
            continue
        chapter_key = str(batch.get("chapter_label") or batch.get("file") or f"batch {batch.get('batch', '')}").strip()
        if not chapter_key:
            chapter_key = "unknown"
        chapter = chapter_counts[chapter_key]
        for translated in read_jsonl(translated_path):
            row_id = str(translated.get("id", ""))
            source_row = batch_rows.get(row_id, {})
            source_text = _row_source_text(source_row)
            translated_text = html_text(str(translated.get("translated_html", "")))
            row_count += 1
            chapter["rows"] += 1
            source_char_count += len(re.sub(r"\s+", "", source_text))
            unchanged_source_chars += _unchanged_source_char_count(source_text, translated_text)

            for segment in _long_untranslated_segments(source_text, translated_text):
                issue = _quality_issue(
                    batch,
                    row_id,
                    "long-untranslated-segment",
                    "blocking",
                    "Long source-language segment remains in translated text",
                    sample=segment,
                )
                issues.append(issue)
                long_segments.append(issue)
                _count_chapter_issue(chapter, issue)

            punctuation_issue = _punctuation_quote_drift(batch, row_id, source_text, translated_text)
            if punctuation_issue:
                issues.append(punctuation_issue)
                punctuation_drift.append(punctuation_issue)
                _count_chapter_issue(chapter, punctuation_issue)

            for issue in _person_name_drift(batch, row_id, source_text, translated_text, person_terms):
                issues.append(issue)
                person_name_drift.append(issue)
                _count_chapter_issue(chapter, issue)

    blocking_count = len([issue for issue in issues if issue.get("severity") == "blocking"])
    nonblocking_count = len(issues) - blocking_count
    chapter_summary = _chapter_summary(chapter_counts)
    return {
        "row_count": row_count,
        "untranslated_ratio": round(unchanged_source_chars / source_char_count, 4) if source_char_count else 0.0,
        "long_untranslated_segments": long_segments[:50],
        "punctuation_quote_drift": punctuation_drift[:50],
        "person_name_drift": person_name_drift[:50],
        "chapter_summary_consistency": chapter_summary,
        "sampled_llm_reviewer_findings": [],
        "issue_count": len(issues),
        "blocking_count": blocking_count,
        "nonblocking_count": nonblocking_count,
        "issues": issues[:200],
    }


def _empty_quality_report() -> dict:
    return {
        "row_count": 0,
        "untranslated_ratio": 0.0,
        "long_untranslated_segments": [],
        "punctuation_quote_drift": [],
        "person_name_drift": [],
        "chapter_summary_consistency": {"chapters": 0, "chapters_with_issues": 0, "worst": []},
        "sampled_llm_reviewer_findings": [],
        "issue_count": 0,
        "blocking_count": 0,
        "nonblocking_count": 0,
        "issues": [],
    }


def _row_source_text(row: dict) -> str:
    source_text = str(row.get("source_text", ""))
    if source_text:
        return source_text
    return html_text(str(row.get("source_html", "")))


def _unchanged_source_char_count(source_text: str, translated_text: str) -> int:
    seen: set[str] = set()
    total = 0
    for match in SOURCE_WORD_RE.finditer(source_text):
        word = match.group(0).strip(".,;:!?()[]{}")
        key = word.lower()
        if len(word) < 4 or key in seen:
            continue
        seen.add(key)
        if contains_term(translated_text, word):
            total += len(word)
    return total


def _long_untranslated_segments(source_text: str, translated_text: str) -> list[str]:
    source_compact = re.sub(r"\s+", " ", source_text).lower()
    segments: list[str] = []
    for match in LONG_UNTRANSLATED_RE.finditer(translated_text):
        segment = re.sub(r"\s+", " ", match.group(0)).strip()
        if len(segment) < 28:
            continue
        if segment.lower() in source_compact:
            segments.append(segment[:220])
    return segments[:3]


def _punctuation_quote_drift(batch: dict, row_id: str, source_text: str, translated_text: str) -> dict | None:
    source_profile = _punctuation_profile(source_text)
    translated_profile = _punctuation_profile(translated_text)
    changed = {
        key: {"source": value, "translated": translated_profile.get(key, 0)}
        for key, value in source_profile.items()
        if value and translated_profile.get(key, 0) != value
    }
    if not changed:
        return None
    return _quality_issue(
        batch,
        row_id,
        "punctuation-quote-drift",
        "nonblocking",
        "Punctuation or quote balance changed from source text",
        details=changed,
    )


def _punctuation_profile(text: str) -> dict[str, int]:
    return {
        "quotes": sum(1 for char in text if char in QUOTE_CHARS),
        "open_parentheses": text.count("(") + text.count("[") + text.count("{") + text.count("（"),
        "close_parentheses": text.count(")") + text.count("]") + text.count("}") + text.count("）"),
        "sentence_punctuation": sum(1 for char in text if char in SENTENCE_PUNCTUATION),
    }


def _person_name_drift(
    batch: dict,
    row_id: str,
    source_text: str,
    translated_text: str,
    person_terms: list[dict],
) -> list[dict]:
    issues = []
    for term in person_terms:
        source = term.get("source", "")
        translation = term.get("translation", "")
        aliases = [source, *term.get("aliases", [])]
        if not source or not translation:
            continue
        if not any(contains_term(source_text, alias) for alias in aliases):
            continue
        if translation in translated_text or any(contains_term(translated_text, alias) for alias in aliases):
            continue
        issues.append(
            _quality_issue(
                batch,
                row_id,
                "person-name-drift",
                "nonblocking",
                f"Person name {source} is present in source but neither source nor translation appears in output",
                source=source,
                translation=translation,
            )
        )
    return issues


def _quality_issue(
    batch: dict,
    row_id: str,
    kind: str,
    severity: str,
    message: str,
    **details: object,
) -> dict:
    issue = {
        "batch": batch.get("batch"),
        "row_id": row_id,
        "kind": kind,
        "severity": severity,
        "message": message,
    }
    issue.update({key: value for key, value in details.items() if value not in (None, "", [], {})})
    return issue


def _count_chapter_issue(chapter: dict, issue: dict) -> None:
    chapter["issues"] += 1
    if issue.get("severity") == "blocking":
        chapter["blocking"] += 1
    else:
        chapter["nonblocking"] += 1


def _chapter_summary(chapter_counts: dict[str, dict]) -> dict:
    worst = [
        {"chapter": chapter, **counts}
        for chapter, counts in chapter_counts.items()
        if counts.get("issues", 0)
    ]
    worst.sort(key=lambda item: (item["blocking"], item["issues"], item["rows"]), reverse=True)
    return {
        "chapters": len(chapter_counts),
        "chapters_with_issues": len(worst),
        "worst": worst[:10],
    }

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
