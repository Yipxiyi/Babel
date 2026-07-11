<p align="center">
  <img src="docs/assets/brand/babel-icon.png" alt="Babel icon" width="116" height="116">
</p>

<h1 align="center">Babel</h1>

<p align="center">
  Layout-preserving ebook translation pipeline for agentic, chapter-by-chapter workflows.
</p>

<p align="center">
  <strong>Normalize to EPUB. Preserve XHTML. Translate in batches. Export your format.</strong>
</p>

<p align="center">
  English | <a href="README.zh-CN.md">简体中文</a>
</p>

---

Babel turns an ebook into structured translation batches, rebuilds a validated EPUB intermediate, then exports the final translated book in the format you choose.

It is designed for workflows where a main agent maintains a global glossary and context ledger while Codex/subagents translate independent chapter batches in parallel. The self-hosted Web/job runtime can also translate batches automatically with concurrent provider calls. The core pipeline is model-agnostic; the Web/job layer can call user-configured providers such as OpenAI-compatible endpoints or Anthropic Claude.

## Why Babel

Most quick ebook translation scripts flatten a book into text and destroy the reading experience. Babel normalizes inputs to EPUB, then works directly on EPUB internals:

- Preserves chapter files, spine order, CSS, images, links, anchors, IDs, and inline emphasis.
- Extracts only human-readable XHTML blocks into JSONL batches.
- Generates a glossary scaffold, optionally seeds known-name decisions from a glossary preset, drafts missing term translations when a Web provider is configured, and creates worker instructions before translation begins.
- Validates each translated batch before it can be applied.
- Runs Web translations with configurable batch concurrency, timeout, retries, and failed-job resume.
- Rejects common fake/placeholder translations such as `第 N 段译文`.
- Repackages a validated EPUB intermediate with the required uncompressed `mimetype` entry.
- Exports the final translated book as EPUB or a Calibre-backed target format.
- Audits the output for missing manifest items, broken internal links, and missing anchors.

## Supported Input Formats

Babel normalizes every input into an EPUB workspace before translation. Input support is split by fidelity:

- Native: `.epub`.
- Built in: `.txt`, `.html`, `.htm`, `.xhtml`.
- Calibre-backed: `.mobi`, `.azw`, `.azw3`, `.kfx`, `.pdf`, `.fb2`, `.docx`, `.rtf`, `.cbz`, `.cbr`, and related formats supported by `ebook-convert`.

EPUB gives the best layout preservation because Babel can operate on the existing XHTML structure. Other formats are first converted to EPUB, then processed by the same validation pipeline.

## Supported Output Formats

- Native: `.epub`.
- Calibre-backed: `.mobi`, `.azw3`, `.pdf`, `.docx`, `.txt`, `.html`, `.htmlz`, `.kepub`, `.rtf`, `.fb2`.

EPUB output is dependency-free. Non-EPUB output is exported from the validated EPUB intermediate and requires Calibre `ebook-convert` unless you use the Docker image.

`--output-epub` is still accepted as a compatibility alias, but new workflows should use `--output-book` plus `--output-format`.

The `--output-book` path must include the selected extension, for example `output_zh-CN.pdf` with `--output-format pdf`.

## Status

Babel is early-stage but usable. It now includes a dependency-free CLI core, a React/Vite self-hosted Web UI, Docker deployment, a Codex skill, and a Claude MCP server.

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

The Web UI lets you upload an ebook, choose the final output format, auto-draft missing glossary translations with a configured provider, import/export glossary terms from the review modal, choose concurrency/timeout/retry settings, watch terminal-style progress, resume failed jobs, and download the translated book plus report.

The top-right `Guide` button opens the recommended operation flow. The language toggle supports English and Simplified Chinese and is saved in `localStorage`.

Docker includes Calibre for MOBI/AZW3/PDF/DOCX/CBZ input conversion and non-EPUB output export. Private job data is stored in the `babel-data` volume. Do not expose this server publicly without setting `BABEL_WEB_TOKEN` behind HTTPS or another trusted authentication layer. Web uploads are limited to 200 MB by default; set `BABEL_MAX_UPLOAD_MB` to raise or lower the limit.

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

Build the React UI into the Python package static directory:

```bash
npm install --prefix web
npm test --prefix web
npm run build --prefix web
```

Start the bundled Web UI:

```bash
babel-server --host 127.0.0.1 --port 7860 --data-dir ./babel-data
```

Open `http://127.0.0.1:7860`.

For frontend development, run the backend and Vite dev server separately:

```bash
babel-server --host 127.0.0.1 --port 7860 --data-dir ./babel-data
npm run dev --prefix web
```

Vite runs on `http://127.0.0.1:5173` and proxies `/api` to the local Babel server.

Supported MVP providers:

- `OpenAI Compatible`: any `/v1/chat/completions`-compatible endpoint.
- `OpenAI Responses`: OpenAI `/v1/responses` with optional JSON Schema output.
- `Anthropic Claude`: Anthropic Messages API.
- `Ollama`: local OpenAI-compatible models at `http://127.0.0.1:11434/v1` by default.
- `DeepL` and `Google Translate`: HTML-aware machine translation adapters for users who prefer dedicated MT providers.
- `Fake Dry Run`: deterministic local output for testing the pipeline without spending tokens.

OpenAI-compatible providers can optionally request JSON Schema responses with the Web settings `Structured JSON output` toggle or the MCP `structured_output_enabled` field. Anthropic remains prompt-constrained, and Babel still falls back to its tolerant parser for returned text.

Translation Memory can be enabled from Web settings or MCP with `memory_enabled` plus a stable `memory_project_id`. Babel stores exact source-snippet matches under `BABEL_DATA_DIR/translation_memory/<project>.json`, validates every hit against the current source row, skips provider calls for valid hits, and writes successful translated rows back to the project memory.

The quality report combines locked-glossary repair with deterministic QA fields for untranslated ratio, long untranslated source-language segments, punctuation/quote drift, person-name drift, and chapter-level issue grouping. The Web validation panel shows the summary and the full JSON is downloadable as `AI QA JSON`.

Runtime controls:

- `Concurrency`: default `3`, clamped to `1..8`.
- `Request timeout`: default `300` seconds.
- `Retries`: default `1`; retryable failures are timeout, HTTP 429, and HTTP 5xx. HTTP 400/401 are not retried.
- `Requests / min` and `Tokens / min`: optional provider rate limits shared by the job.
- `Budget limit` plus input/output cost per 1M tokens: optional spend guard. Babel estimates each request before it is sent, stops before crossing the budget, and failed jobs can be resumed after raising the limit.
- Failed batches continue to be recorded while other batches keep running. After all workers finish, use `Resume Translation` to rerun only missing, damaged, invalid, or budget-stopped batch outputs.

Security and upload controls:

- `BABEL_WEB_TOKEN`: optional bearer token for all `/api/*` routes, including downloads. Send `Authorization: Bearer <token>` or `X-Babel-Token: <token>`. The token is never returned by `/api/meta` or provider settings responses.
- `BABEL_MAX_UPLOAD_MB`: maximum upload size in megabytes. Default: `200`. Oversized uploads return HTTP 413 before multipart parsing.
- `BABEL_CONVERSION_TIMEOUT`: Calibre `ebook-convert` timeout in seconds for conversion-backed input or output. Default: `600`.

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

Use `--glossary-preset edge-chronicles` to seed the glossary from the bundled Edge Chronicles preset, or pass a path to a compatible JSON preset. Without a preset, Babel keeps extraction generic and leaves project-specific terms for review.

Use `--max-chars` or `--max-tokens` with `prepare` to split batches by approximate source size in addition to the legacy `--max-blocks` cap. This helps keep provider prompts below context limits for books with very long paragraphs.

Manage Translation Memory stores from the CLI when you need import/export outside the Web UI:

```bash
babel-epub memory stats --project-id my-series --data-dir ./babel-data
babel-epub memory export --project-id my-series --data-dir ./babel-data --file ./my-series-memory.json
babel-epub memory import --project-id my-series --data-dir ./babel-data --file ./my-series-memory.json
```

Import or export structured glossary terms as CSV, TBX, Markdown preset, or JSON. Imports preserve `approved`/`pending`/`ignored` status and `locked` decisions, then regenerate the compact Markdown prompt surface used by workers:

```bash
babel-epub import-glossary --work-dir ./babel_work/book --file ./glossary.csv --mode upsert
babel-epub export-glossary --work-dir ./babel_work/book --file ./glossary.tbx
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

TXT/HTML work without external tools. MOBI/AZW/PDF/DOCX/CBZ and similar formats require Calibre `ebook-convert` unless you use the Docker image. Use `--conversion-timeout` or `BABEL_CONVERSION_TIMEOUT` to bound long conversions.

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

Apply translations and export EPUB:

```bash
babel-epub apply \
  --work-dir ./babel_work/book \
  --output-book ./output_zh-CN.epub \
  --output-format epub \
  --title "Translated Title" \
  --language zh-CN
```

Export another format, for example PDF:

```bash
babel-epub apply \
  --work-dir ./babel_work/book \
  --output-book ./output_zh-CN.pdf \
  --output-format pdf \
  --title "Translated Title" \
  --language zh-CN
```

Audit the validated EPUB package. For non-EPUB final output, audit the intermediate EPUB in the work directory:

```bash
babel-epub audit \
  --epub ./babel_work/book/output.epub \
  --out ./babel_work/book/pipeline/epub_audit.json
```

Write a report:

```bash
babel-epub report \
  --work-dir ./babel_work/book \
  --output-book ./output_zh-CN.epub \
  --glossary ./translation_glossary.md \
  --report ./translation_report.md
```

## Recommended Agent Workflow

1. Run `prepare`.
2. Review `name_candidates.json`.
3. Let AI draft missing glossary translations when a provider is configured.
4. Review the glossary, approve stable name and term decisions, and ignore noise.
5. Main agent maintains `translation_context.md`.
6. Dispatch batch workers with `WORKER_INSTRUCTIONS.md`, the glossary, and relevant prior context.
7. Require every worker to run `validate-batch`.
8. Main agent runs `validate-batches`.
9. Run `apply`, then `audit`.
10. Scan the final book and intermediate EPUB for placeholder text and long untranslated passages.

See [docs/CODEX_WORKFLOW.md](docs/CODEX_WORKFLOW.md) for the multi-agent operating model.

## Codex Skill

Install by copying the skill folder:

```bash
mkdir -p ~/.codex/skills/babel
cp integrations/codex/babel/SKILL.md ~/.codex/skills/babel/SKILL.md
```

Then ask Codex to use Babel for ebook translation. The skill points Codex at the local CLI/Web workflow and enforces glossary, context, validation, selected output format, and EPUB-preservation rules.

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

The `start_translation` MCP tool accepts optional `resume`, `batch_filter`, `max_concurrency`, `request_timeout`, `max_retries`, `structured_output_enabled`, `memory_enabled`, `memory_project_id`, `memory_path`, `ai_qa_enabled`, `auto_title_enabled`, provider rate limits, and budget/cost fields. MCP also exposes `list_jobs`, `artifact_path`, `read_glossary_terms`, `update_glossary_terms`, `import_glossary`, `export_glossary`, `resume_failed_job`, and `retry_batch`; `retry_batch` clears the selected translated JSONL and resumes with a one-batch filter.

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
npm test --prefix web
npm run build --prefix web
docker compose config  # optional, requires Docker
```

## License

MIT. See [LICENSE](LICENSE).
