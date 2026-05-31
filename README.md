<p align="center">
  <img src="docs/assets/brand/babel-icon.svg" alt="Babel icon" width="116" height="116">
</p>

<h1 align="center">Babel</h1>

<p align="center">
  Layout-preserving EPUB translation pipeline for agentic, chapter-by-chapter workflows.
</p>

<p align="center">
  <strong>Unpack EPUB. Preserve XHTML. Translate in batches. Validate hard. Rebuild clean.</strong>
</p>

---

Babel turns an EPUB into structured translation batches, then rebuilds a valid EPUB after the translated XHTML snippets pass validation.

It is designed for workflows where a main agent maintains a global glossary and context ledger while Codex/subagents translate independent chapter batches in parallel. Babel does not call a translation API and does not require a third-party orchestration framework. It gives you the file structure, validation gates, and EPUB packaging layer.

## Why Babel

Most quick EPUB translation scripts flatten a book into text and destroy the reading experience. Babel works directly on the EPUB internals:

- Preserves chapter files, spine order, CSS, images, links, anchors, IDs, and inline emphasis.
- Extracts only human-readable XHTML blocks into JSONL batches.
- Generates a glossary scaffold and worker instructions before translation begins.
- Validates each translated batch before it can be applied.
- Rejects common fake/placeholder translations such as `第 N 段译文`.
- Repackages the EPUB with the required uncompressed `mimetype` entry.
- Audits the output for missing manifest items, broken internal links, and missing anchors.

## Status

Babel is early-stage but usable. The core CLI is dependency-free Python and is covered by a minimal EPUB round-trip test.

## Install From Source

```bash
git clone https://github.com/Yipxiyi/Babel.git
cd Babel
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Verify the CLI:

```bash
babel-epub --help
python3 -m unittest discover -s tests -v
```

## Quick Start

Prepare a private working directory from your EPUB:

```bash
babel-epub prepare \
  --input-epub ./input.epub \
  --work-dir ./babel_work/book \
  --glossary ./translation_glossary.md \
  --target-language "Simplified Chinese" \
  --max-blocks 120
```

Babel creates:

```txt
babel_work/book/
  source/                    # unpacked EPUB tree, private
  pipeline/
    blocks.jsonl             # all extracted translatable XHTML blocks
    batches/                 # batch inputs for translators/agents
    translated/              # translated batch outputs go here
    batch_manifest.json
    chapters.json
    name_candidates.json
    translation_context.md
    WORKER_INSTRUCTIONS.md
translation_glossary.md
```

Translate each batch by writing matching JSONL rows into `pipeline/translated/`.

Input row:

```json
{"id":"OEBPS/chapter1.xhtml::0001","source_html":"<p>Hello <em>world</em>.</p>"}
```

Output row:

```json
{"id":"OEBPS/chapter1.xhtml::0001","translated_html":"<p>你好，<em>世界</em>。</p>"}
```

Validate one batch:

```bash
babel-epub validate-batch \
  --pipeline-dir ./babel_work/book/pipeline \
  --batch batches/batch_001_chapter1_01.jsonl \
  --output translated/batch_001_chapter1_01.translated.jsonl
```

Validate all batches:

```bash
babel-epub validate-batches --pipeline-dir ./babel_work/book/pipeline
```

Apply translations and rebuild the EPUB:

```bash
babel-epub apply \
  --work-dir ./babel_work/book \
  --output-epub ./output_zh-CN.epub \
  --title "Translated Title" \
  --language zh-CN
```

Audit the finished EPUB:

```bash
babel-epub audit \
  --epub ./output_zh-CN.epub \
  --out ./babel_work/book/pipeline/epub_audit.json
```

Write a report:

```bash
babel-epub report \
  --work-dir ./babel_work/book \
  --output-epub ./output_zh-CN.epub \
  --glossary ./translation_glossary.md \
  --report ./translation_report.md
```

## Recommended Agent Workflow

1. Run `prepare`.
2. Review `name_candidates.json`.
3. Fill `translation_glossary.md` with stable name and term decisions.
4. Main agent maintains `translation_context.md`.
5. Dispatch batch workers with `WORKER_INSTRUCTIONS.md`, the glossary, and relevant prior context.
6. Require every worker to run `validate-batch`.
7. Main agent runs `validate-batches`.
8. Run `apply`, then `audit`.
9. Scan the final EPUB for placeholder text and long untranslated passages.

See [docs/CODEX_WORKFLOW.md](docs/CODEX_WORKFLOW.md) for the multi-agent operating model.

## Plugin Or Skill?

Babel is intentionally a standalone CLI project, not a Codex plugin.

A plugin would be the wrong abstraction for the core problem: EPUB extraction, validation, and packaging should be reusable from any terminal, CI job, or agent environment. A Codex skill can document how to orchestrate Babel, and Babel may later ship an optional skill template, but the source of truth should remain this CLI.

## Repository Layout

```txt
src/babel_epub/          # dependency-free CLI and EPUB pipeline
tests/                   # minimal EPUB round-trip tests
docs/                   # OpenArc product, design, brand, architecture docs
docs/assets/brand/       # icon and identity assets
```

## Legal And Safety Notes

Babel is a format-preserving tool. It does not grant translation rights. Only translate books or documents you own, have permission to process, or are legally allowed to transform. Do not commit private EPUBs, translated books, or generated workspaces to a public repository.

The default `.gitignore` excludes `*.epub`, JSONL batches, generated reports, and local work directories.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile src/babel_epub/*.py
```

## License

MIT. See [LICENSE](LICENSE).
