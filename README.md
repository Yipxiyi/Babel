<p align="center">
  <img src="docs/assets/brand/babel-icon.svg" alt="Babel icon" width="116" height="116">
</p>

<h1 align="center">Babel</h1>

<p align="center">
  Layout-preserving ebook translation pipeline for agentic, chapter-by-chapter workflows.
</p>

<p align="center">
  <strong>Unpack EPUB. Preserve XHTML. Translate in batches. Validate hard. Rebuild clean.</strong>
</p>

<p align="center">
  English | <a href="README.zh-CN.md">简体中文</a>
</p>

---

Babel turns an ebook into structured translation batches, then rebuilds a valid EPUB after the translated XHTML snippets pass validation.

It is designed for workflows where a main agent maintains a global glossary and context ledger while Codex/subagents translate independent chapter batches in parallel. The core pipeline is model-agnostic; the Web/job layer can call user-configured providers such as OpenAI-compatible endpoints or Anthropic Claude.

## Why Babel

Most quick ebook translation scripts flatten a book into text and destroy the reading experience. Babel normalizes inputs to EPUB, then works directly on EPUB internals:

- Preserves chapter files, spine order, CSS, images, links, anchors, IDs, and inline emphasis.
- Extracts only human-readable XHTML blocks into JSONL batches.
- Generates a glossary scaffold and worker instructions before translation begins.
- Validates each translated batch before it can be applied.
- Rejects common fake/placeholder translations such as `第 N 段译文`.
- Repackages the EPUB with the required uncompressed `mimetype` entry.
- Audits the output for missing manifest items, broken internal links, and missing anchors.

## Supported Input Formats

Babel outputs EPUB. Input support is split by fidelity:

- Native: `.epub`.
- Built in: `.txt`, `.html`, `.htm`, `.xhtml`.
- Calibre-backed: `.mobi`, `.azw`, `.azw3`, `.kfx`, `.pdf`, `.fb2`, `.docx`, `.rtf`, `.cbz`, `.cbr`, and related formats supported by `ebook-convert`.

EPUB gives the best layout preservation because Babel can operate on the existing XHTML structure. Other formats are first converted to EPUB, then processed by the same validation pipeline.

## Status

Babel is early-stage but usable. It now includes a dependency-free CLI core, a self-hosted Web UI, Docker deployment, a Codex skill, and a Claude MCP server.

## Easiest Start: Docker Web UI

```bash
git clone https://github.com/Yipxiyi/Babel.git
cd Babel
docker compose up --build
```

Open:

```txt
http://127.0.0.1:7860
```

The Web UI lets you upload an ebook, review/edit the glossary, configure an API provider, watch progress, and download the translated EPUB plus report.

Docker includes Calibre for MOBI/AZW3/PDF/DOCX/CBZ conversion and stores private job data in the `babel-data` volume. Do not expose this server publicly without adding authentication.

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
babel-server --help
python3 -m unittest discover -s tests -v
```

## Web UI From Source

```bash
babel-server --host 127.0.0.1 --port 7860 --data-dir ./babel-data
```

Open `http://127.0.0.1:7860`.

Supported MVP providers:

- `OpenAI Compatible`: any `/v1/chat/completions`-compatible endpoint.
- `Anthropic Claude`: Anthropic Messages API.
- `Fake Dry Run`: deterministic local output for testing the pipeline without spending tokens.

## CLI Quick Start

Prepare a private working directory from your EPUB:

```bash
babel-epub prepare \
  --input-book ./input.epub \
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

For non-EPUB input:

```bash
babel-epub prepare --input-book ./input.azw3 --work-dir ./babel_work/book
```

TXT/HTML work without external tools. MOBI/AZW/PDF/DOCX/CBZ and similar formats require Calibre `ebook-convert` unless you use the Docker image.

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

## Codex Skill

Install by copying the skill folder:

```bash
mkdir -p ~/.codex/skills/babel
cp integrations/codex/babel/SKILL.md ~/.codex/skills/babel/SKILL.md
```

Then ask Codex to use Babel for ebook translation. The skill points Codex at the local CLI/Web workflow and enforces glossary, context, validation, and EPUB-preservation rules.

## Claude Desktop MCP

Install Babel, then add this MCP server to Claude Desktop:

```json
{
  "mcpServers": {
    "babel": {
      "command": "babel-mcp",
      "env": {
        "BABEL_DATA_DIR": "/absolute/path/to/babel-data"
      }
    }
  }
}
```

See [integrations/claude](integrations/claude).

## Plugin Or Skill?

Babel is intentionally a standalone package with CLI/Web/MCP adapters, not a Codex plugin.

A plugin would be the wrong abstraction for the core problem: EPUB extraction, validation, and packaging should be reusable from any terminal, Web server, Docker container, CI job, or agent environment. Codex and Claude integrations call the same core instead of duplicating it.

## Repository Layout

```txt
src/babel_epub/              # dependency-free core, job engine, Web server, MCP server
integrations/codex/babel/    # Codex skill
integrations/claude/         # Claude Desktop MCP docs/config
tests/                       # minimal EPUB/job/Web tests
docs/                        # OpenArc product, design, brand, architecture docs
docs/assets/brand/           # icon and identity assets
```

## Legal And Safety Notes

Babel is a format-preserving tool. It does not grant translation rights. Only translate books or documents you own, have permission to process, or are legally allowed to transform. Do not commit private books, translated books, or generated workspaces to a public repository.

The default `.gitignore` excludes `*.epub`, JSONL batches, generated reports, and local work directories. If you use other private book formats, keep them out of git as well.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile src/babel_epub/*.py
docker compose config  # optional, requires Docker
```

## License

MIT. See [LICENSE](LICENSE).
