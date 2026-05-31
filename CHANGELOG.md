# Changelog

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
