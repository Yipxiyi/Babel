# Changelog

## 0.6.0 - 2026-06-03

### Added

- Automatic concurrent batch translation in the Web/job runtime with default `max_concurrency=3` and an API/MCP range of `1..8`.
- Provider request timeout and retry controls with retry events for timeout, HTTP 429, and HTTP 5xx failures.
- Job state fields for `active_batches`, `failed_batches`, and `max_concurrency`.
- Web controls for concurrency, request timeout, and retries.

### Changed

- Failed batches no longer stop the whole run immediately; other batches continue, then the job ends as failed with resume support for only missing or invalid batches.
- Provider configuration errors are validated before a job enters running state.
- Project icon updated to the warm Babel tower mark.

## 0.5.0 - 2026-06-02

### Added

- React, Vite, and Tailwind Web UI served by `babel-server` as packaged static assets.
- Bilingual English and Simplified Chinese UI with persisted language selection.
- Guide modal with step-by-step operation flow, upload focus, and current job navigation actions.
- Project PNG icon based on the approved Babel mark.
- Terminal-style job progress log with failed batch visibility and resume action.
- Persistent job events, `current_batch`, `failed_batch`, `last_active_at`, and resume support for failed jobs.

### Changed

- Docker now builds the React Web UI in a Node stage before installing the Python package.
- Web UI now auto-loads the latest job after refresh and keeps existing API routes compatible.

## 0.4.0 - 2026-06-01

### Added

- User-selectable final output formats for CLI, Web, job engine, and Claude MCP workflows.
- Native EPUB output remains dependency-free; `.mobi`, `.azw3`, `.pdf`, `.docx`, `.txt`, `.html`, `.htmlz`, `.kepub`, `.rtf`, and `.fb2` export use Calibre `ebook-convert`.
- Output format metadata at `pipeline/output_format.json`.
- Web UI output format selector and generic output download flow.
- Validation that rejects missing or mismatched `--output-format` and output file suffix combinations.

## 0.3.0 - 2026-06-01

### Added

- Multi-format ebook input normalization.
- Native internal conversion for `.txt`, `.html`, `.htm`, and `.xhtml`.
- Calibre-backed conversion for mainstream ebook/document formats including `.mobi`, `.azw`, `.azw3`, `.kfx`, `.pdf`, `.fb2`, `.docx`, `.rtf`, `.cbz`, and `.cbr`.
- Input format metadata at `pipeline/input_format.json`.
- Web upload accept list for supported ebook formats.
- Docker image installs Calibre so conversion-backed formats work in the self-hosted container.

## 0.2.0 - 2026-05-31

### Added

- Self-hosted Web UI via `babel-server`.
- Local job engine for upload, glossary review, batch translation, validation, apply, audit, reports, and downloads.
- OpenAI-compatible, Anthropic, and fake dry-run provider adapters.
- Dockerfile and Docker Compose deployment.
- Claude MCP server via `babel-mcp`.
- Codex skill integration under `integrations/codex/babel`.
- Web/job/provider tests.

## 0.1.0 - 2026-05-31

### Added

- Initial dependency-free EPUB translation pipeline.
- `prepare`, `validate-batch`, `validate-batches`, `apply`, `audit`, `report`, and `worker-instructions` CLI commands.
- Glossary scaffold, context ledger, name candidate extraction, and batch worker instructions.
- Placeholder/filler translation rejection.
- Minimal EPUB round-trip tests.
- MIT license and OpenArc governance docs.
