---
name: babel
description: Use Babel to translate EPUB books while preserving layout, using the local CLI or self-hosted Web server.
---

# Babel Codex Skill

Use this skill when the user asks to translate an EPUB or another ebook format, batch ebook translation, preserve ebook formatting, or run Babel.

## Requirements

- Babel installed from source or available on PATH.
- Private ebook files must stay out of git.
- EPUB is handled directly. TXT/HTML are converted internally. MOBI/AZW/PDF/DOCX/CBZ and similar formats require Calibre `ebook-convert`, included in Babel's Docker image.
- Use `translation_glossary.md` and `translation_context.md` as global coordination files.

## CLI Workflow

```bash
babel-epub prepare --input-book ./input.epub --work-dir ./babel_work/book --glossary ./translation_glossary.md --target-language "Simplified Chinese"
babel-epub validate-batches --pipeline-dir ./babel_work/book/pipeline
babel-epub apply --work-dir ./babel_work/book --output-epub ./output_zh-CN.epub --title "Translated Title" --language zh-CN
babel-epub audit --epub ./output_zh-CN.epub --out ./babel_work/book/pipeline/epub_audit.json
```

## Web Workflow

```bash
babel-server --host 127.0.0.1 --port 7860 --data-dir ./babel-data
```

Open `http://127.0.0.1:7860`, upload the EPUB, review the glossary, configure the provider, start translation, then download the output EPUB and report.

## Agent Rules

- Build or update the glossary before dispatching chapter batches.
- Preserve XHTML root tags, IDs, classes, href/src links, anchors, images, and inline emphasis.
- Translate only human-readable text.
- Do not flatten EPUB into plain text.
- Do not commit EPUBs, JSONL batches, or generated workspaces.
- Verify with `validate-batches`, `audit`, and `unzip -t` before claiming completion.
