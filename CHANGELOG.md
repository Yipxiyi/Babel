# Changelog

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
