"""Layout-preserving EPUB-normalized translation pipeline.

Babel deliberately keeps the core pipeline dependency-free. It prepares JSONL
batches for human or agent translators, validates translated XHTML snippets,
applies them back into the original EPUB tree, and audits the packaged output.
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from .adaptive import build_preparation_plan
from .formats import convert_epub_to_output, normalize_to_epub, write_input_format_metadata, write_output_format_metadata
from .glossary import build_glossary_terms, normalize_term, read_glossary_terms, render_glossary_markdown, should_skip_name_candidate, write_glossary_terms
from .glossary_io import export_glossary_file, import_glossary_file, merge_glossary_terms


XHTML_NS = "http://www.w3.org/1999/xhtml"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
XML_NS = "http://www.w3.org/XML/1998/namespace"
EPUB_NS = "http://www.idpf.org/2007/ops"

NS = {
    "x": XHTML_NS,
    "opf": OPF_NS,
    "dc": DC_NS,
    "ncx": NCX_NS,
    "c": CONTAINER_NS,
    "xml": XML_NS,
    "epub": EPUB_NS,
}

ET.register_namespace("", XHTML_NS)
ET.register_namespace("opf", OPF_NS)
ET.register_namespace("dc", DC_NS)
ET.register_namespace("dcterms", "http://purl.org/dc/terms/")
ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")

TEXT_TAGS = {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "blockquote",
    "figcaption",
    "td",
    "th",
    "dt",
    "dd",
}
SKIP_TAGS = {"script", "style", "svg", "math"}
STRUCTURAL_ATTRS = {"id", "class", "href", "src", "alt", "title"}
HTML_DOCUMENT_EXTS = {".xhtml", ".html", ".htm"}
RESOURCE_ATTRS_BY_TAG = {
    "audio": ("src",),
    "embed": ("src",),
    "img": ("src",),
    "image": ("href", "src"),
    "link": ("href",),
    "object": ("data",),
    "script": ("src",),
    "source": ("src", "srcset"),
    "track": ("src",),
    "video": ("src", "poster"),
}
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’.-]*")
NAME_RE = re.compile(
    r"\b[A-Z][a-z]+(?:[’'-][A-Z]?[a-z]+)?"
    r"(?:\s+[A-Z][a-z]+(?:[’'-][A-Z]?[a-z]+)?){0,3}\b"
)
ESTIMATED_CHARS_PER_TOKEN = 4

PLACEHOLDER_RE = re.compile(
    r"(?:第\s*[0-9一二三四五六七八九十百]+\s*段\s*译文|"
    r"段译文|>\s*译文\s*<|"
    r"[。！？；：，、]\s*译文\s*[。！？；：，、<]|"
    r"\b(?:translated text|translation goes here|placeholder)\b)",
    re.IGNORECASE,
)
COMMON_NAME_FALSE_POSITIVES = {
    "A",
    "About",
    "After",
    "All",
    "An",
    "And",
    "As",
    "At",
    "Before",
    "But",
    "By",
    "Chapter",
    "Do",
    "For",
    "From",
    "He",
    "Her",
    "His",
    "I",
    "If",
    "In",
    "It",
    "No",
    "Not",
    "Of",
    "On",
    "Or",
    "Prologue",
    "She",
    "So",
    "The",
    "Then",
    "This",
    "To",
    "We",
    "What",
    "When",
    "Where",
    "Who",
    "With",
    "You",
}


@dataclass(frozen=True)
class EpubPaths:
    root: Path
    opf_rel: str
    opf_path: Path
    opf_dir: Path



def safe_extract(archive: zipfile.ZipFile, target_dir: Path) -> None:
    """Extract a ZIP/EPUB archive without allowing path traversal or unsafe entries."""
    root = target_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    for info in archive.infolist():
        name = info.filename
        if not name or "\x00" in name:
            raise ValueError("unsafe zip entry name")
        normalized = name.replace("\\", "/")
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
            raise ValueError(f"unsafe absolute zip entry: {name}")
        parts = [part for part in normalized.split("/") if part]
        if any(part == ".." for part in parts):
            raise ValueError(f"unsafe zip entry path traversal: {name}")
        mode = (info.external_attr >> 16) & 0o777777
        if mode:
            entry_type = stat.S_IFMT(mode)
            if entry_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise ValueError(f"unsafe zip entry file type: {name}")
        destination = (root / normalized).resolve()
        try:
            destination.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"unsafe zip entry outside target: {name}") from exc
        if info.is_dir() or normalized.endswith("/"):
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, destination.open("wb") as output:
            shutil.copyfileobj(source, output)


def local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[1]
    return tag


def normalize_space(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def element_text(element: ET.Element) -> str:
    return normalize_space("".join(element.itertext()))


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def xml_parse(path: Path) -> ET.ElementTree:
    return ET.parse(path)


def has_translatable_text(text: str) -> bool:
    value = normalize_space(text)
    if not value:
        return False
    if re.fullmatch(r"page_\d+", value, flags=re.IGNORECASE):
        return False
    if re.fullmatch(r"[\d\s.,:;!?()\-–—_#]+", value):
        return False
    if re.fullmatch(r"#[0-9A-Fa-f]{3,8}", value):
        return False
    if re.fullmatch(r"[.#]?[A-Za-z_][A-Za-z0-9_-]*\s*[:=]\s*[-#\w.,%() ]+", value):
        return False
    return any(unicodedata.category(char).startswith("L") for char in value)


def clone_without_namespace(element: ET.Element) -> ET.Element:
    clone = ET.Element(local_name(element.tag), dict(element.attrib))
    clone.text = element.text
    clone.tail = element.tail
    for child in list(element):
        clone.append(clone_without_namespace(child))
    return clone


def element_to_snippet(element: ET.Element) -> str:
    clone = clone_without_namespace(element)
    return ET.tostring(clone, encoding="unicode", method="xml", short_empty_elements=True)


def parse_snippet(snippet: str) -> ET.Element:
    wrapped = f'<root xmlns="{XHTML_NS}">{snippet}</root>'
    try:
        root = ET.fromstring(wrapped)
    except ET.ParseError as exc:
        raise ValueError(f"invalid translated_html XML snippet: {exc}") from exc
    children = list(root)
    if len(children) != 1:
        raise ValueError("translated_html must contain exactly one root element")
    child = children[0]
    child.tail = None
    return child


def container_opf(root: Path) -> EpubPaths:
    container = root / "META-INF" / "container.xml"
    if not container.exists():
        raise FileNotFoundError(f"missing {container}")
    tree = xml_parse(container)
    rootfile = tree.find(".//c:rootfile", NS)
    if rootfile is None or not rootfile.get("full-path"):
        raise ValueError("container.xml does not declare an OPF rootfile")
    opf_rel = rootfile.get("full-path", "")
    opf_path = root / opf_rel
    if not opf_path.exists():
        raise FileNotFoundError(f"declared OPF file does not exist: {opf_path}")
    return EpubPaths(root=root, opf_rel=opf_rel, opf_path=opf_path, opf_dir=opf_path.parent)


def opf_manifest_and_spine(paths: EpubPaths) -> tuple[dict[str, dict], list[str]]:
    tree = xml_parse(paths.opf_path)
    manifest: dict[str, dict] = {}
    for item in tree.findall(".//opf:manifest/opf:item", NS):
        item_id = item.get("id")
        href = item.get("href")
        if not item_id or not href:
            continue
        manifest[item_id] = {
            "href": href,
            "media_type": item.get("media-type", ""),
            "properties": item.get("properties", ""),
            "path": (paths.opf_dir / href).resolve(),
            "rel_path": (paths.opf_dir / href).relative_to(paths.root).as_posix(),
        }
    spine = [
        itemref.get("idref", "")
        for itemref in tree.findall(".//opf:spine/opf:itemref", NS)
        if itemref.get("idref")
    ]
    return manifest, spine


def toc_labels(paths: EpubPaths, manifest: dict[str, dict]) -> dict[str, str]:
    labels: dict[str, str] = {}
    ncx_items = [item for item in manifest.values() if item["media_type"] == "application/x-dtbncx+xml"]
    if ncx_items:
        ncx_path = paths.root / ncx_items[0]["rel_path"]
        tree = xml_parse(ncx_path)
        for nav_point in tree.findall(".//ncx:navPoint", NS):
            text_el = nav_point.find("./ncx:navLabel/ncx:text", NS)
            content_el = nav_point.find("./ncx:content", NS)
            if text_el is None or content_el is None or not content_el.get("src"):
                continue
            src = content_el.get("src", "").split("#", 1)[0]
            rel = (paths.opf_dir / src).relative_to(paths.root).as_posix()
            labels.setdefault(rel, normalize_space(text_el.text))

    nav_items = [
        item
        for item in manifest.values()
        if item["media_type"] == "application/xhtml+xml"
        and ("nav" in str(item.get("properties", "")).split() or item["rel_path"].lower().endswith("nav.xhtml"))
    ]
    for item in nav_items:
        nav_path = paths.root / item["rel_path"]
        try:
            nav_root = xml_parse(nav_path).getroot()
        except ET.ParseError:
            continue
        for nav in nav_root.iter():
            if local_name(nav.tag) != "nav":
                continue
            nav_type = nav.attrib.get(f"{{{EPUB_NS}}}type") or nav.attrib.get("type") or ""
            if nav_type and "toc" not in nav_type.split():
                continue
            for anchor in nav.iter():
                if local_name(anchor.tag) != "a" or not anchor.attrib.get("href"):
                    continue
                src = anchor.attrib.get("href", "").split("#", 1)[0]
                if not src:
                    continue
                rel = (nav_path.parent / src).resolve().relative_to(paths.root.resolve()).as_posix()
                label = element_text(anchor)
                if label:
                    labels.setdefault(rel, label)
    return labels


def iter_xhtml_body_elements(path: Path) -> Iterable[ET.Element]:
    tree = xml_parse(path)
    root = tree.getroot()
    body = root.find(".//x:body", NS)
    if body is None:
        return []
    return list(body.iter())


def translatable_elements(path: Path) -> list[ET.Element]:
    elements: list[ET.Element] = []
    for element in iter_xhtml_body_elements(path):
        tag = local_name(element.tag)
        if tag in SKIP_TAGS or tag not in TEXT_TAGS:
            continue
        text = element_text(element)
        if has_translatable_text(text):
            elements.append(element)
    return elements


def classify_doc(label: str) -> str:
    if re.match(r"Chapter\s+\d+\b", label or "", flags=re.IGNORECASE):
        return "chapter"
    lowered = (label or "").lower()
    if any(token in lowered for token in ("contents", "cover", "title", "copyright", "praise")):
        return "front_matter"
    if any(token in lowered for token in ("acknowledg", "about the author", "author", "also by")):
        return "back_matter"
    return "unknown"


def build_chapters(src_dir: Path, out_dir: Path) -> list[dict]:
    paths = container_opf(src_dir)
    manifest, spine = opf_manifest_and_spine(paths)
    labels = toc_labels(paths, manifest)
    chapters: list[dict] = []
    order = 0
    for item_id in spine:
        item = manifest.get(item_id)
        if not item or item["media_type"] not in {"application/xhtml+xml", "text/html"}:
            continue
        order += 1
        rel_path = item["rel_path"]
        label = labels.get(rel_path, "")
        file_path = src_dir / rel_path
        block_count = len(translatable_elements(file_path))
        chapters.append(
            {
                "order": order,
                "item_id": item_id,
                "file": rel_path,
                "label": label,
                "kind": classify_doc(label),
                "block_count": block_count,
            }
        )
    (out_dir / "chapters.json").write_text(
        json.dumps(chapters, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return chapters


def extract_blocks(src_dir: Path, out_dir: Path) -> list[dict]:
    chapters = build_chapters(src_dir, out_dir)
    blocks: list[dict] = []
    per_file_index: defaultdict[str, int] = defaultdict(int)
    for chapter in chapters:
        rel_path = chapter["file"]
        file_path = src_dir / rel_path
        for element in translatable_elements(file_path):
            per_file_index[rel_path] += 1
            index = per_file_index[rel_path]
            block_id = f"{rel_path}::{index:04d}"
            blocks.append(
                {
                    "id": block_id,
                    "order": chapter["order"],
                    "file": rel_path,
                    "seq": index,
                    "tag": local_name(element.tag),
                    "chapter_label": chapter["label"],
                    "chapter_kind": chapter["kind"],
                    "source_text": element_text(element),
                    "source_html": element_to_snippet(element),
                }
            )
    write_jsonl(out_dir / "blocks.jsonl", blocks)
    return blocks


def estimate_block_chars(block: dict) -> int:
    value = str(block.get("source_html") or block.get("source_text") or "")
    return max(1, len(value))


def estimate_tokens_from_chars(char_count: int) -> int:
    return max(1, (char_count + ESTIMATED_CHARS_PER_TOKEN - 1) // ESTIMATED_CHARS_PER_TOKEN)


def normalized_batch_limits(
    max_blocks: int,
    max_chars: int | str | None = None,
    max_tokens: int | str | None = None,
) -> tuple[int, int | None]:
    try:
        block_limit = int(max_blocks)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_blocks must be a positive integer") from exc
    if block_limit <= 0:
        raise ValueError("max_blocks must be a positive integer")

    char_limits: list[int] = []
    if max_chars not in (None, ""):
        try:
            char_limit = int(max_chars)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_chars must be a positive integer") from exc
        if char_limit <= 0:
            raise ValueError("max_chars must be a positive integer")
        char_limits.append(char_limit)
    if max_tokens not in (None, ""):
        try:
            token_limit = int(max_tokens)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_tokens must be a positive integer") from exc
        if token_limit <= 0:
            raise ValueError("max_tokens must be a positive integer")
        char_limits.append(token_limit * ESTIMATED_CHARS_PER_TOKEN)
    return block_limit, min(char_limits) if char_limits else None


def iter_batch_chunks(
    file_blocks: list[dict],
    max_blocks: int,
    max_chars: int | str | None = None,
    max_tokens: int | str | None = None,
) -> list[list[dict]]:
    block_limit, char_limit = normalized_batch_limits(max_blocks, max_chars=max_chars, max_tokens=max_tokens)
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0
    for block in file_blocks:
        block_chars = estimate_block_chars(block)
        would_exceed_blocks = len(current) >= block_limit
        would_exceed_chars = char_limit is not None and current_chars + block_chars > char_limit
        if current and (would_exceed_blocks or would_exceed_chars):
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(block)
        current_chars += block_chars
    if current:
        chunks.append(current)
    return chunks


def write_batches(
    out_dir: Path,
    max_blocks: int,
    max_chars: int | str | None = None,
    max_tokens: int | str | None = None,
) -> list[dict]:
    blocks = read_jsonl(out_dir / "blocks.jsonl")
    by_file: dict[str, list[dict]] = defaultdict(list)
    for block in blocks:
        by_file[block["file"]].append(block)

    batch_dir = out_dir / "batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    batches: list[dict] = []
    batch_number = 0
    for file_name, file_blocks in sorted(by_file.items(), key=lambda item: (item[1][0]["order"], item[0])):
        chunk_index = 0
        for chunk in iter_batch_chunks(file_blocks, max_blocks, max_chars=max_chars, max_tokens=max_tokens):
            chunk_index += 1
            batch_number += 1
            safe_stem = Path(file_name).stem
            batch_name = f"batch_{batch_number:03d}_{safe_stem}_{chunk_index:02d}.jsonl"
            batch_path = batch_dir / batch_name
            write_jsonl(batch_path, chunk)
            translated_path = out_dir / "translated" / batch_name.replace(".jsonl", ".translated.jsonl")
            source_chars = sum(estimate_block_chars(block) for block in chunk)
            batches.append(
                {
                    "batch": batch_number,
                    "file": file_name,
                    "chapter_label": chunk[0].get("chapter_label", ""),
                    "chapter_kind": chunk[0].get("chapter_kind", ""),
                    "start_seq": chunk[0]["seq"],
                    "end_seq": chunk[-1]["seq"],
                    "block_count": len(chunk),
                    "source_chars": source_chars,
                    "estimated_tokens": estimate_tokens_from_chars(source_chars),
                    "input": batch_path.relative_to(out_dir).as_posix(),
                    "output": translated_path.relative_to(out_dir).as_posix(),
                    "status": "pending",
                }
            )
    (out_dir / "batch_manifest.json").write_text(
        json.dumps(batches, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return batches


def extract_name_candidates(out_dir: Path, min_count: int) -> list[dict]:
    counter: Counter[str] = Counter()
    for block in read_jsonl(out_dir / "blocks.jsonl"):
        for match in NAME_RE.findall(block["source_text"]):
            term = normalize_term(match)
            if should_skip_name_candidate(term):
                continue
            counter[term] += 1
    rows = [{"term": term, "count": count} for term, count in counter.most_common() if count >= min_count]
    (out_dir / "name_candidates.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return rows


def default_glossary(target_language: str, out_dir: Path, glossary_preset: str | None = None) -> str:
    extract_name_candidates(out_dir, min_count=3)
    terms = build_glossary_terms(out_dir, target_language, glossary_preset=glossary_preset)
    return render_glossary_markdown(target_language, terms)


def worker_instructions(target_language: str) -> str:
    return f"""# Babel Batch Translation Worker Instructions

You are translating one EPUB batch into {target_language}.

Input rows are JSONL records with `id`, `source_text`, and `source_html`.
Output must be JSONL with exactly the same row count and exactly the same `id` values.

For each row:

- Write `translated_html`, not plain text.
- Preserve the root HTML tag, structural attributes, IDs, anchors, href/src links, image references, CSS classes, and inline emphasis tags.
- Translate only human-readable text inside the snippet.
- Do not translate filenames, IDs, classes, attributes, URLs, code-like values, or anchors.
- Do not summarize, omit, rewrite, or add commentary.
- Use the project glossary and context ledger.
- If a phrase is ambiguous, infer from chapter context and record uncertainty outside the EPUB, not inside `translated_html`.

Expected output row shape:

```json
{{"id":"OEBPS/chapter.xhtml::0001","translated_html":"<p>译文</p>"}}
```

Before returning a batch, run:

```bash
babel-epub validate-batch --pipeline-dir PATH/TO/pipeline --batch batches/BATCH.jsonl --output translated/BATCH.translated.jsonl
```
"""


def command_prepare(args: argparse.Namespace) -> dict:
    input_value = getattr(args, "input_book", None) or getattr(args, "input_epub", None)
    if not input_value:
        raise ValueError("prepare requires --input-book or --input-epub")
    input_book = Path(input_value)
    work_dir = Path(args.work_dir)
    src_dir = work_dir / "source"
    pipeline_dir = work_dir / "pipeline"
    if not input_book.exists():
        raise FileNotFoundError(input_book)
    if src_dir.exists() and not args.force:
        raise FileExistsError(f"{src_dir} already exists; rerun with --force to replace it")
    if args.force and src_dir.exists():
        shutil.rmtree(src_dir)
    if args.force and pipeline_dir.exists():
        shutil.rmtree(pipeline_dir)

    src_dir.mkdir(parents=True, exist_ok=True)
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    input_metadata = normalize_to_epub(
        input_book,
        work_dir,
        converter_path=getattr(args, "converter_path", None),
        conversion_timeout=getattr(args, "conversion_timeout", None),
    )
    write_input_format_metadata(pipeline_dir, input_metadata)
    with zipfile.ZipFile(work_dir / "input.epub") as archive:
        safe_extract(archive, src_dir)

    blocks = extract_blocks(src_dir, pipeline_dir)
    adaptive_plan = build_preparation_plan(
        filename=str(getattr(args, "source_filename", "") or input_book.name),
        input_format=str(input_metadata.get("input_format", input_book.suffix.lower())),
        file_size=input_book.stat().st_size,
        blocks=blocks,
        adaptive_enabled=bool(getattr(args, "adaptive_enabled", False)),
        requested_batch_chars=getattr(args, "max_chars", None),
    )
    batch_char_limit = (
        adaptive_plan["preparation"]["batch_char_limit"]
        if adaptive_plan["enabled"]
        else getattr(args, "max_chars", None)
    )
    batches = write_batches(
        pipeline_dir,
        args.max_blocks,
        max_chars=batch_char_limit,
        max_tokens=getattr(args, "max_tokens", None),
    )
    adaptive_plan["preparation"]["estimated_batches"] = len(batches)
    (pipeline_dir / "adaptive_plan.json").write_text(
        json.dumps(adaptive_plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    glossary_path = Path(args.glossary)
    glossary_path.write_text(
        default_glossary(
            args.target_language,
            pipeline_dir,
            glossary_preset=getattr(args, "glossary_preset", None),
        ),
        encoding="utf-8",
    )
    (pipeline_dir / "translation_context.md").write_text(
        "# Translation Context Ledger\n\n"
        "Maintain global continuity here: relationships, timeline, unresolved ambiguities, "
        "name decisions, voice notes, and repaired-batch findings.\n",
        encoding="utf-8",
    )
    (pipeline_dir / "WORKER_INSTRUCTIONS.md").write_text(
        worker_instructions(args.target_language),
        encoding="utf-8",
    )
    print(f"prepared {len(blocks)} translatable blocks in {len(batches)} batches under {work_dir}")
    return {
        "input_metadata": input_metadata,
        "blocks": blocks,
        "batches": batches,
        "adaptive_plan": adaptive_plan,
    }


def structural_tokens(element: ET.Element) -> list[tuple[str, str, str]]:
    tokens: list[tuple[str, str, str]] = []
    for descendant in element.iter():
        for attr in STRUCTURAL_ATTRS:
            value = descendant.attrib.get(attr)
            if value is not None:
                tokens.append((local_name(descendant.tag), attr, value))
    return tokens


def descendant_structure_issues(source: ET.Element, translated: ET.Element) -> list[str]:
    source_tokens = structural_tokens(source)
    translated_tokens = structural_tokens(translated)
    if source_tokens == translated_tokens:
        return []
    return [
        "structural id/href/src tokens changed: "
        f"source={source_tokens!r} translated={translated_tokens!r}"
    ]


def attrs_compatible(source: ET.Element, translated: ET.Element) -> list[str]:
    issues: list[str] = []
    if local_name(source.tag) != local_name(translated.tag):
        issues.append(f"root tag changed: {local_name(source.tag)} -> {local_name(translated.tag)}")
    for key, source_value in source.attrib.items():
        if key in STRUCTURAL_ATTRS and translated.attrib.get(key) != source_value:
            issues.append(f"attribute {key!r} changed: {source_value!r} -> {translated.attrib.get(key)!r}")
    issues.extend(descendant_structure_issues(source, translated))
    return issues


def validate_translation_rows(batch_rows: list[dict], translated_rows: list[dict]) -> list[str]:
    issues: list[str] = []
    if len(translated_rows) != len(batch_rows):
        issues.append(
            f"translated row count mismatch: expected {len(batch_rows)} got {len(translated_rows)}"
        )

    source_ids = [str(row.get("id", "")) for row in batch_rows]
    translated_ids = [str(row.get("id", "")) for row in translated_rows]
    source_counts = Counter(source_ids)
    translated_counts = Counter(translated_ids)
    for row_id, count in sorted(source_counts.items()):
        if not row_id:
            issues.append("source row missing id")
        elif count > 1:
            issues.append(f"duplicate source row id: {row_id}")
    for row_id, count in sorted(translated_counts.items()):
        if not row_id:
            issues.append("translated row missing id")
        elif count > 1:
            issues.append(f"duplicate translated row id: {row_id}")

    source_id_set = set(source_ids)
    translated_id_set = set(translated_ids)
    for missing in sorted(source_id_set - translated_id_set):
        if missing:
            issues.append(f"missing translated row for {missing}")
    for extra in sorted(translated_id_set - source_id_set):
        if extra:
            issues.append(f"unexpected translated row id: {extra}")
    if translated_ids != source_ids:
        issues.append("translated row order changed: expected source batch order")

    by_id: dict[str, dict] = {}
    for row in translated_rows:
        row_id = str(row.get("id", ""))
        if row_id and translated_counts[row_id] == 1:
            by_id[row_id] = row

    for source in batch_rows:
        source_id = str(source.get("id", ""))
        if not source_id:
            continue
        row = by_id.get(source_id)
        if row is None:
            continue
        html = row.get("translated_html")
        if not isinstance(html, str) or not html.strip():
            issues.append(f"missing translated_html for {source_id}")
            continue
        try:
            source_el = parse_snippet(str(source["source_html"]))
            translated_el = parse_snippet(html)
        except ValueError as exc:
            issues.append(f"{source_id}: {exc}")
            continue
        issues.extend(f"{source_id}: {issue}" for issue in attrs_compatible(source_el, translated_el))
        translated_text = element_text(translated_el)
        if PLACEHOLDER_RE.search(html) or PLACEHOLDER_RE.search(translated_text):
            issues.append(f"{source_id}: placeholder translation remains")
        if WORD_RE.search(translated_text) and len(re.findall(r"[A-Za-z]{4,}", translated_text)) > 12:
            issues.append(f"{source_id}: possible long untranslated Latin text remains")
    return issues


def command_validate_batch(args: argparse.Namespace) -> None:
    pipeline_dir = Path(args.pipeline_dir)
    batch_path = Path(args.batch)
    if not batch_path.is_absolute():
        batch_path = pipeline_dir / batch_path
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = pipeline_dir / output_path
    issues = validate_translation_rows(read_jsonl(batch_path), read_jsonl(output_path))
    report = {
        "batch": batch_path.as_posix(),
        "output": output_path.as_posix(),
        "issue_count": len(issues),
        "issues": issues,
    }
    report_path = output_path.with_suffix(output_path.suffix + ".validation.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if issues:
        print(f"{output_path} failed validation with {len(issues)} issues", file=sys.stderr)
        raise SystemExit(1)
    print(f"validated {output_path}")


def command_validate_batches(args: argparse.Namespace) -> None:
    pipeline_dir = Path(args.pipeline_dir)
    manifest = json.loads((pipeline_dir / "batch_manifest.json").read_text(encoding="utf-8"))
    all_issues: list[str] = []
    completed = 0
    for batch in manifest:
        batch_path = pipeline_dir / batch["input"]
        out_path = pipeline_dir / batch["output"]
        if not out_path.exists():
            all_issues.append(f"missing output: {out_path}")
            continue
        issues = validate_translation_rows(read_jsonl(batch_path), read_jsonl(out_path))
        if issues:
            all_issues.extend(issues)
        else:
            completed += 1
    report = {
        "batch_count": len(manifest),
        "completed_without_issues": completed,
        "issue_count": len(all_issues),
        "issues": all_issues[:500],
    }
    (pipeline_dir / "batch_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if all_issues:
        print(f"validation failed with {len(all_issues)} issues; see batch_validation.json", file=sys.stderr)
        raise SystemExit(1)
    print(f"validated {completed} translated batches")


def collect_translations(pipeline_dir: Path) -> dict[str, dict]:
    manifest = json.loads((pipeline_dir / "batch_manifest.json").read_text(encoding="utf-8"))
    translations: dict[str, dict] = {}
    for batch in manifest:
        batch_path = pipeline_dir / batch["input"]
        out_path = pipeline_dir / batch["output"]
        if not out_path.exists():
            raise FileNotFoundError(f"missing translated batch: {out_path}")
        issues = validate_translation_rows(read_jsonl(batch_path), read_jsonl(out_path))
        if issues:
            raise ValueError(f"{out_path} has validation issues:\n" + "\n".join(issues[:20]))
        for row in read_jsonl(out_path):
            translations[row["id"]] = row
    return translations


def parent_of(root: ET.Element, target: ET.Element) -> ET.Element | None:
    for parent in root.iter():
        for child in list(parent):
            if child is target:
                return parent
    return None


def replace_element(parent: ET.Element, old: ET.Element, new: ET.Element) -> None:
    children = list(parent)
    for idx, child in enumerate(children):
        if child is old:
            new.tail = old.tail
            parent.remove(old)
            parent.insert(idx, new)
            return
    raise ValueError("old child not found in parent")


def apply_translations_to_tree(source_dir: Path, output_dir: Path, pipeline_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.copytree(source_dir, output_dir)
    translations = collect_translations(pipeline_dir)
    blocks = read_jsonl(pipeline_dir / "blocks.jsonl")
    by_file: dict[str, list[dict]] = defaultdict(list)
    for block in blocks:
        by_file[block["file"]].append(block)

    for rel_path, source_blocks in by_file.items():
        file_path = output_dir / rel_path
        tree = xml_parse(file_path)
        root = tree.getroot()
        body = root.find(".//x:body", NS)
        if body is None:
            continue
        elements = [
            element
            for element in body.iter()
            if local_name(element.tag) in TEXT_TAGS and has_translatable_text(element_text(element))
        ]
        if len(elements) != len(source_blocks):
            raise ValueError(f"{rel_path}: block count changed during apply")
        for element, source in zip(elements, source_blocks):
            translated = translations[source["id"]]
            new_element = parse_snippet(translated["translated_html"])
            parent = parent_of(root, element)
            if parent is None:
                raise ValueError(f"{source['id']}: cannot replace root element")
            replace_element(parent, element, new_element)
        tree.write(file_path, encoding="utf-8", xml_declaration=True, short_empty_elements=True)


def update_metadata(epub_dir: Path, title: str | None, language: str | None) -> None:
    paths = container_opf(epub_dir)
    tree = xml_parse(paths.opf_path)
    root = tree.getroot()
    title_el = root.find(".//dc:title", NS)
    lang_el = root.find(".//dc:language", NS)
    if title and title_el is not None:
        title_el.text = title
    if language and lang_el is not None:
        lang_el.text = language
    tree.write(paths.opf_path, encoding="utf-8", xml_declaration=True, short_empty_elements=True)

    manifest, _ = opf_manifest_and_spine(paths)
    ncx_items = [item for item in manifest.values() if item["media_type"] == "application/x-dtbncx+xml"]
    if title and ncx_items:
        ncx_path = epub_dir / ncx_items[0]["rel_path"]
        ncx_tree = xml_parse(ncx_path)
        doc_title = ncx_tree.find(".//ncx:docTitle/ncx:text", NS)
        if doc_title is not None:
            doc_title.text = title
        ncx_tree.write(ncx_path, encoding="utf-8", xml_declaration=True, short_empty_elements=True)


def package_epub(epub_dir: Path, output_epub: Path) -> None:
    mimetype = epub_dir / "mimetype"
    if not mimetype.exists():
        raise FileNotFoundError(f"missing {mimetype}")
    output_epub.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_epub, "w") as archive:
        archive.write(mimetype, "mimetype", compress_type=zipfile.ZIP_STORED)
        for path in sorted(epub_dir.rglob("*")):
            if path.is_dir() or path == mimetype:
                continue
            archive.write(path, path.relative_to(epub_dir).as_posix(), compress_type=zipfile.ZIP_DEFLATED)


def command_apply(args: argparse.Namespace) -> None:
    work_dir = Path(args.work_dir)
    source_dir = work_dir / "source"
    pipeline_dir = work_dir / "pipeline"
    translated_dir = work_dir / "translated_epub_tree"
    intermediate_epub = work_dir / "output.epub"
    output_value = getattr(args, "output_book", None) or getattr(args, "output_epub", None)
    if not output_value:
        raise ValueError("apply requires --output-book or --output-epub")
    output_book = Path(output_value)
    output_format = getattr(args, "output_format", None) or output_book.suffix or ".epub"
    apply_translations_to_tree(source_dir, translated_dir, pipeline_dir)
    update_metadata(translated_dir, args.title, args.language)
    package_epub(translated_dir, intermediate_epub)
    metadata = convert_epub_to_output(
        intermediate_epub,
        output_book,
        output_format=output_format,
        converter_path=getattr(args, "converter_path", None),
        conversion_timeout=getattr(args, "conversion_timeout", None),
    )
    write_output_format_metadata(pipeline_dir, metadata)
    print(f"wrote {output_book}")


def is_external_reference(value: str) -> bool:
    stripped = value.strip()
    if not stripped or stripped.startswith("#"):
        return True
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", stripped))


def srcset_candidates(value: str) -> list[str]:
    candidates: list[str] = []
    for part in value.split(","):
        url = part.strip().split(" ", 1)[0]
        if url:
            candidates.append(url)
    return candidates


def href_target(base_file: str, href: str) -> str:
    clean = href.split("#", 1)[0]
    if not clean:
        return ""
    return posixpath.normpath(posixpath.join(posixpath.dirname(base_file), clean))


def id_index(epub_dir: Path) -> dict[str, set[str]]:
    index: dict[str, set[str]] = defaultdict(set)
    for path in (p for p in epub_dir.rglob("*") if p.suffix.lower() in HTML_DOCUMENT_EXTS):
        rel = path.relative_to(epub_dir).as_posix()
        try:
            root = xml_parse(path).getroot()
        except ET.ParseError:
            continue
        for element in root.iter():
            element_id = element.attrib.get("id")
            if element_id:
                index[rel].add(element_id)
    return index


def audit_epub_dir(epub_dir: Path, source_epub: Path | None = None) -> dict:
    paths = container_opf(epub_dir)
    manifest, spine = opf_manifest_and_spine(paths)
    missing_manifest = [
        item["rel_path"] for item in manifest.values() if not (epub_dir / item["rel_path"]).exists()
    ]
    xhtml_spine = [
        manifest[item_id]["rel_path"]
        for item_id in spine
        if item_id in manifest and manifest[item_id]["media_type"] in {"application/xhtml+xml", "text/html"}
    ]
    ids = id_index(epub_dir)
    missing_page_anchors: list[str] = []
    broken_internal_links: list[str] = []
    broken_resource_links: list[str] = []
    external_links = 0
    ncx_navpoints = 0
    ncx_page_targets = 0

    ncx_items = [item for item in manifest.values() if item["media_type"] == "application/x-dtbncx+xml"]
    if ncx_items:
        ncx_rel = ncx_items[0]["rel_path"]
        ncx_tree = xml_parse(epub_dir / ncx_rel)
        ncx_navpoints = len(ncx_tree.findall(".//ncx:navPoint", NS))
        page_targets = ncx_tree.findall(".//ncx:pageTarget", NS)
        ncx_page_targets = len(page_targets)
        for target in page_targets:
            content = target.find("./ncx:content", NS)
            if content is None or not content.get("src") or "#" not in content.get("src", ""):
                continue
            src = content.get("src", "")
            file_part, anchor = src.split("#", 1)
            rel = (paths.opf_dir / file_part).relative_to(epub_dir).as_posix()
            if anchor not in ids.get(rel, set()):
                missing_page_anchors.append(src)

    for path in (p for p in epub_dir.rglob("*") if p.suffix.lower() in HTML_DOCUMENT_EXTS):
        rel = path.relative_to(epub_dir).as_posix()
        try:
            root = xml_parse(path).getroot()
        except ET.ParseError as exc:
            broken_internal_links.append(f"{rel}: XML parse error: {exc}")
            continue
        for element in root.iter():
            tag = local_name(element.tag)
            href = element.attrib.get("href")
            if href:
                if is_external_reference(href):
                    external_links += 1
                else:
                    target_rel = href_target(rel, href)
                    if target_rel:
                        target_path = epub_dir / target_rel
                        if not target_path.exists():
                            broken_internal_links.append(f"{rel}: missing href {href}")
                        elif "#" in href:
                            anchor = href.split("#", 1)[1]
                            if anchor and anchor not in ids.get(target_rel, set()):
                                broken_internal_links.append(f"{rel}: missing anchor {href}")
            for attr in RESOURCE_ATTRS_BY_TAG.get(tag, ()):  # local media/resource references
                raw_value = element.attrib.get(attr)
                if not raw_value:
                    continue
                values = srcset_candidates(raw_value) if attr == "srcset" else [raw_value]
                for value in values:
                    if is_external_reference(value):
                        continue
                    target_rel = href_target(rel, value)
                    if target_rel and not (epub_dir / target_rel).exists():
                        broken_resource_links.append(f"{rel}: missing resource {value}")

    images = [
        path.relative_to(epub_dir).as_posix()
        for path in epub_dir.rglob("*")
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
    ]
    mimetype_ok = (epub_dir / "mimetype").read_text(encoding="utf-8", errors="replace") == "application/epub+zip"
    zip_mimetype_first = None
    zip_mimetype_stored = None
    if source_epub and source_epub.exists():
        with zipfile.ZipFile(source_epub) as archive:
            infos = archive.infolist()
            zip_mimetype_first = bool(infos and infos[0].filename == "mimetype")
            mime_info = next((info for info in infos if info.filename == "mimetype"), None)
            zip_mimetype_stored = bool(mime_info and mime_info.compress_type == zipfile.ZIP_STORED)

    return {
        "opf": paths.opf_rel,
        "manifest_count": len(manifest),
        "missing_manifest_items": missing_manifest,
        "spine_count": len(spine),
        "spine_xhtml_count": len(xhtml_spine),
        "ncx_navpoints": ncx_navpoints,
        "ncx_page_targets": ncx_page_targets,
        "missing_page_anchors": sorted(set(missing_page_anchors)),
        "broken_internal_links": broken_internal_links,
        "broken_resource_links": sorted(set(broken_resource_links)),
        "external_links": external_links,
        "image_count": len(images),
        "images": images,
        "mimetype_ok": mimetype_ok,
        "zip_mimetype_first": zip_mimetype_first,
        "zip_mimetype_stored": zip_mimetype_stored,
    }


def command_audit(args: argparse.Namespace) -> None:
    epub_path = Path(args.epub)
    if not epub_path.exists():
        raise FileNotFoundError(epub_path)
    with zipfile.ZipFile(epub_path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"zip integrity failed at {bad}")
        with tempfile.TemporaryDirectory(prefix="babel_epub_audit_") as tmp:
            tmp_dir = Path(tmp)
            safe_extract(archive, tmp_dir)
            report = audit_epub_dir(tmp_dir, source_epub=epub_path)
    report["zip_integrity"] = "passed"
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    issue_count = (
        len(report["missing_manifest_items"])
        + len(report["missing_page_anchors"])
        + len(report["broken_internal_links"])
        + len(report.get("broken_resource_links", []))
    )
    print(f"wrote {out_path}; structural issue count: {issue_count}")
    if issue_count:
        raise SystemExit(1)


def command_report(args: argparse.Namespace) -> None:
    work_dir = Path(args.work_dir)
    pipeline_dir = work_dir / "pipeline"
    chapters = json.loads((pipeline_dir / "chapters.json").read_text(encoding="utf-8"))
    manifest = json.loads((pipeline_dir / "batch_manifest.json").read_text(encoding="utf-8"))
    completed = [batch for batch in manifest if (pipeline_dir / batch["output"]).exists()]
    output_value = getattr(args, "output_book", None) or getattr(args, "output_epub", None)
    if not output_value:
        raise ValueError("report requires --output-book or --output-epub")
    output_book = Path(output_value)
    output_epub = work_dir / "output.epub"
    output_format_path = pipeline_dir / "output_format.json"
    output_format = "unknown"
    output_conversion = "unknown"
    if output_format_path.exists():
        output_metadata = json.loads(output_format_path.read_text(encoding="utf-8"))
        output_format = output_metadata.get("output_format", "unknown")
        output_conversion = output_metadata.get("output_conversion_method", "unknown")
    zip_ok = False
    image_count = 0
    xhtml_count = 0
    if output_epub.exists():
        with zipfile.ZipFile(output_epub) as archive:
            zip_ok = archive.testzip() is None
            names = archive.namelist()
            image_count = len(
                [name for name in names if name.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"))]
            )
            xhtml_count = len([name for name in names if name.lower().endswith((".xhtml", ".html"))])
    report = f"""# Translation Report

- Output file: `{output_book.resolve()}`
- Output format: `{output_format}` via `{output_conversion}`
- EPUB zip integrity: {'passed' if zip_ok else 'not verified or failed'}
- Spine XHTML files: {len(chapters)}
- XHTML/HTML files in output archive: {xhtml_count}
- Translation batches: {len(manifest)}
- Completed translation batches: {len(completed)}
- Images preserved in output archive: {image_count}
- Glossary: `{Path(args.glossary).resolve()}`

## Validation Summary

- Batch validation should pass before `apply`.
- Run `babel-epub audit --epub {output_epub}` against the intermediate EPUB after packaging.
- Record uncertain translations and glossary changes in the context ledger.
"""
    Path(args.report).write_text(report, encoding="utf-8")
    print(f"wrote {args.report}")


def command_worker_instructions(args: argparse.Namespace) -> None:
    print(worker_instructions(args.target_language))




def command_import_glossary(args: argparse.Namespace) -> None:
    work_dir = Path(args.work_dir)
    imported = import_glossary_file(Path(args.file), default_status=args.default_status, fmt=args.format)
    existing = read_glossary_terms(work_dir)
    merged = merge_glossary_terms(existing, imported, mode=args.mode)
    normalized = write_glossary_terms(work_dir, merged)
    glossary_path = Path(args.glossary)
    glossary_path.write_text(render_glossary_markdown(args.target_language, normalized), encoding="utf-8")
    print(
        f"imported {len(imported)} glossary terms into {work_dir / 'pipeline' / 'glossary_terms.json'} "
        f"({len(normalized)} total)"
    )


def command_export_glossary(args: argparse.Namespace) -> None:
    work_dir = Path(args.work_dir)
    terms = read_glossary_terms(work_dir)
    out_path = export_glossary_file(Path(args.file), terms, target_language=args.target_language, fmt=args.format)
    print(f"exported {len(terms)} glossary terms to {out_path}")

def command_memory(args: argparse.Namespace) -> None:
    from .memory import TranslationMemoryStore, memory_path_for, normalize_memory_project_id

    project_id = normalize_memory_project_id(getattr(args, "project_id", "default"))
    data_dir = Path(getattr(args, "data_dir", None) or os.environ.get("BABEL_DATA_DIR", "./babel-data"))
    store = TranslationMemoryStore(
        memory_path_for(data_dir, project_id=project_id, memory_path=getattr(args, "memory_path", None)),
        project_id=project_id,
    )
    action = args.action
    if action == "stats":
        print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
        return
    if action == "export":
        if not args.file:
            raise ValueError("memory export requires --file")
        out_path = store.export_to(Path(args.file))
        print(f"exported translation memory to {out_path}")
        return
    if action == "import":
        if not args.file:
            raise ValueError("memory import requires --file")
        result = store.import_from(Path(args.file))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    raise ValueError(f"unsupported memory action: {action}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Babel layout-preserving ebook translation pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Normalize a book to EPUB and create translation batches.")
    prepare.add_argument("--input-book", help="Input ebook file. Supports EPUB directly plus TXT/HTML internally and Calibre-backed formats.")
    prepare.add_argument("--input-epub", help="Deprecated alias for --input-book.")
    prepare.add_argument("--work-dir", default="babel_work")
    prepare.add_argument("--glossary", default="translation_glossary.md")
    prepare.add_argument("--target-language", default="Simplified Chinese")
    prepare.add_argument("--converter-path", help="Optional path to Calibre ebook-convert for MOBI/AZW/PDF/etc.")
    prepare.add_argument("--conversion-timeout", type=float, help="Calibre ebook-convert timeout in seconds. Defaults to BABEL_CONVERSION_TIMEOUT or 600.")
    prepare.add_argument("--max-blocks", type=int, default=120)
    prepare.add_argument("--max-chars", type=int, help="Optional approximate source character budget per batch.")
    prepare.add_argument("--max-tokens", type=int, help="Optional estimated token budget per batch; uses a conservative character estimate.")
    prepare.add_argument("--glossary-preset", default="", help="Optional built-in preset name or JSON preset path.")
    prepare.add_argument("--force", action="store_true")
    prepare.set_defaults(func=command_prepare)

    validate = subparsers.add_parser("validate-batches", help="Validate every translated batch.")
    validate.add_argument("--pipeline-dir", default="babel_work/pipeline")
    validate.set_defaults(func=command_validate_batches)

    validate_one = subparsers.add_parser("validate-batch", help="Validate one translated batch.")
    validate_one.add_argument("--pipeline-dir", default="babel_work/pipeline")
    validate_one.add_argument("--batch", required=True)
    validate_one.add_argument("--output", required=True)
    validate_one.set_defaults(func=command_validate_batch)

    apply = subparsers.add_parser("apply", help="Apply translated batches and export the selected output format.")
    apply.add_argument("--work-dir", default="babel_work")
    apply.add_argument("--output-book", help="Final output book path. Defaults to --output-epub for compatibility.")
    apply.add_argument("--output-epub", help="Deprecated alias for --output-book.")
    apply.add_argument(
        "--output-format",
        default="epub",
        help="Output format: epub, mobi, azw3, pdf, docx, txt, html, htmlz, kepub, rtf, fb2.",
    )
    apply.add_argument("--converter-path", help="Optional path to Calibre ebook-convert for non-EPUB output.")
    apply.add_argument("--conversion-timeout", type=float, help="Calibre ebook-convert timeout in seconds. Defaults to BABEL_CONVERSION_TIMEOUT or 600.")
    apply.add_argument("--title")
    apply.add_argument("--language", default="zh-CN")
    apply.set_defaults(func=command_apply)

    audit = subparsers.add_parser("audit", help="Audit EPUB package structure and internal links.")
    audit.add_argument("--epub", required=True)
    audit.add_argument("--out", default="babel_work/pipeline/epub_audit.json")
    audit.set_defaults(func=command_audit)

    report = subparsers.add_parser("report", help="Write a compact translation report.")
    report.add_argument("--work-dir", default="babel_work")
    report.add_argument("--output-book", help="Final output book path. Defaults to --output-epub for compatibility.")
    report.add_argument("--output-epub", help="Deprecated alias for --output-book.")
    report.add_argument("--glossary", default="translation_glossary.md")
    report.add_argument("--report", default="translation_report.md")
    report.set_defaults(func=command_report)

    import_glossary = subparsers.add_parser("import-glossary", help="Import glossary terms from CSV, TBX, Markdown, or JSON.")
    import_glossary.add_argument("--work-dir", default="babel_work")
    import_glossary.add_argument("--file", required=True)
    import_glossary.add_argument("--format", choices=["csv", "tbx", "md", "json"], help="Input format. Defaults to file extension.")
    import_glossary.add_argument("--mode", choices=["upsert", "replace", "append"], default="upsert")
    import_glossary.add_argument("--default-status", choices=["pending", "approved", "ignored"], default="pending")
    import_glossary.add_argument("--target-language", default="Simplified Chinese")
    import_glossary.add_argument("--glossary", default="translation_glossary.md")
    import_glossary.set_defaults(func=command_import_glossary)

    export_glossary = subparsers.add_parser("export-glossary", help="Export structured glossary terms to CSV, TBX, Markdown, or JSON.")
    export_glossary.add_argument("--work-dir", default="babel_work")
    export_glossary.add_argument("--file", required=True)
    export_glossary.add_argument("--format", choices=["csv", "tbx", "md", "json"], help="Output format. Defaults to file extension.")
    export_glossary.add_argument("--target-language", default="Simplified Chinese")
    export_glossary.set_defaults(func=command_export_glossary)

    memory = subparsers.add_parser("memory", help="Manage Translation Memory import/export/statistics.")
    memory.add_argument("action", choices=["stats", "export", "import"])
    memory.add_argument("--project-id", default="default", help="Project or series id for the memory store.")
    memory.add_argument("--data-dir", default=os.environ.get("BABEL_DATA_DIR", "./babel-data"))
    memory.add_argument("--memory-path", help="Explicit memory JSON path. Overrides --data-dir/--project-id.")
    memory.add_argument("--file", help="Import source or export destination JSON/JSONL file.")
    memory.set_defaults(func=command_memory)

    return parser
