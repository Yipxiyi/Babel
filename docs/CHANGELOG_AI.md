# AI Change Log

## 2026-05-31

- Initialized Babel as an OpenArc-governed open-source project.
- Chose standalone CLI over Codex plugin because EPUB transformation and validation should be reusable outside one agent host.
- Migrated the proven EPUB workflow into a generic dependency-free Python package.
- Added README, MIT license, contribution guide, brand/design docs, architecture docs, and a minimal SVG icon.
- Added minimal EPUB round-trip tests and placeholder-rejection coverage.
- Added a self-hosted Web/Docker/agent MVP while preserving the CLI core.
- Added multi-format input normalization while keeping EPUB as the intermediate/output format.
