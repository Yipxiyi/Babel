# Changelog

## 0.8.1 - 2026-07-11

### Changed

- Migrated the Web workbench to HeroUI v3 native buttons, cards, fields, selects, switches, alerts, dialogs, tables, pagination, disclosures, links, chips, and progress indicators.
- Replaced browser-native translation warnings with an accessible HeroUI alert dialog and aligned component styling with HeroUI semantic tokens and variants.
- Improved glossary review accessibility with labeled editable cells, a row header, native search and pagination, and responsive full-width desktop presentation.

## 0.8.0 - 2026-07-11

### Added

- Optional Web/API bearer-token protection via `BABEL_WEB_TOKEN`, covering `/api/*` routes and artifact downloads without exposing the token in frontend metadata.
- Configurable Web upload limit via `BABEL_MAX_UPLOAD_MB` with a 200 MB default and explicit 413 responses for oversized uploads.
- Safe ZIP/EPUB extraction for prepare and audit paths, rejecting traversal, absolute paths, Windows drive paths, symlinks, and other unsafe archive entries.
- EPUB3 `nav.xhtml` table-of-contents label extraction alongside existing EPUB2 NCX support.
- Audit reporting for broken local media/resource references such as image, stylesheet, audio, video, source, object, script, and track links.
- Optional glossary presets via CLI, Web/API jobs, and MCP, with the project-specific Edge Chronicles vocabulary moved out of the default glossary heuristics.
- Dynamic batch sizing via `--max-chars` / `--max-tokens`, Web/API `max_chars`, and MCP prepare parameters, with source-size metadata recorded in `batch_manifest.json`.
- Calibre conversion timeout support via `--conversion-timeout` and `BABEL_CONVERSION_TIMEOUT`.
- Optional OpenAI-compatible JSON Schema response requests via `structured_output_enabled`, exposed in Web settings and MCP.
- Lightweight Web behavior tests via `npm test --prefix web`, covering upload payloads, settings normalization, start/resume payloads, and glossary review state.
- GitHub Actions CI for Python 3.11/3.12 unit tests and compile checks plus Web test/build validation.
- Translation Memory project stores with exact source-snippet reuse, Web/MCP enablement fields, and CLI `babel-epub memory` import/export/stat commands.
- Glossary import/export for CSV, TBX, Markdown preset, and JSON through CLI plus Web glossary modal import/export controls.
- Deterministic QA report fields for untranslated ratio, long untranslated segments, punctuation/quote drift, person-name drift, and chapter-level issue grouping, surfaced in the Web validation panel.
- Provider rate limits, token-cost budgeting, estimated/actual cost summaries, OpenAI Responses, Ollama/local aliases, and DeepL/Google Translate adapters.
- MCP tools for job listing, artifact paths, structured glossary read/update/import/export, failed-job resume, `start_translation` batch filters, and single-batch retry.

### Changed

- Translated JSONL validation now rejects row-count mismatches, duplicate IDs, missing/extra IDs, out-of-order rows, non-string `translated_html`, and structural drift for `id`, `href`, `src`, `class`, `alt`, and `title` attributes.
- Web job startup now marks jobs running under lock before spawning the background worker so repeated start requests cannot create multiple workers for one job.
- Job state is written through a temporary file and atomic replace to reduce partial `job.json` writes, and corrupt existing `job.json` files are skipped during startup.
- Translatable text detection is now Unicode-aware for CJK, Cyrillic, Arabic, and other scripts while still skipping numeric/punctuation-only and style-like values.
- EPUB audits now scan `.xhtml`, `.html`, and `.htm` documents for IDs, internal links, and anchors.
- Job translation now checks enabled Translation Memory before provider calls and writes validated translated rows back to the project memory.
- Structured glossary updates now share one import/export normalization path so statuses and locked decisions survive round trips.
- Web token protection now includes an in-app unlock flow and authenticated artifact downloads.
- Provider validation no longer requires dummy model or API-key values for DeepL, Google Translate, Ollama, or local OpenAI-compatible endpoints.
- Concurrent jobs coordinate provider budgets, rate limits, and shared Translation Memory stores safely.
- EPUB3 navigation labels resolve relative to the navigation document, and TBX round trips preserve non-Chinese target languages.

## 0.7.2 - 2026-06-08

### Added

- Batch translation recovery now retries provider safety rejections in smaller chunks before marking the batch failed.
- Provider JSONL parsing now has a relaxed fallback for malformed XHTML attribute quotes and stray provider prefixes in otherwise recoverable row objects.
- Web/API glossary autofill action that drafts missing pending term translations with the configured provider while preserving human-approved, edited, and ignored glossary rows.
- Completed Web jobs now show provider usage statistics when the upstream API returns token usage.

### Changed

- Glossary/name candidate extraction now reuses the structured glossary noise filter and skips common modern dialogue, bookish sentence-start, exclamation, weekday, social-media, and family-address false positives.
- AI QA summaries and the validation panel now distinguish blocking untranslated terms from non-blocking locked-translation drift.
- Glossary review now avoids duplicate modal headings, keeps the close action with the filter controls, adds one-click approval for non-ignored terms, shows animated AI autofill progress, and simplifies the validation status icon styling.
- Web language setup now uses a preset dropdown, derives metadata language automatically, localizes Chinese guide step titles, and shows rough time estimates for glossary drafting and translation.
- EPUB chapter classification now recognizes chapter labels with title suffixes such as `Chapter 1 - THE GREAT STORM CHAMBER LIBRARY`.
- Web glossary review now defaults to a compact readiness summary and opens the full editable table in a modal.
- Starting translation with pending or empty glossary draft terms now shows a soft confirmation instead of silently proceeding.

## 0.7.0 - 2026-06-03

### Added

- Local provider settings persistence with `has_api_key`-only public API responses, allowing self-hosted users to leave the API key field blank after the first successful configuration.
- Structural repair for translated rows that restores missing `id`, `href`, and `src` XHTML tokens before strict validation.
- Restart recovery that marks interrupted `running` jobs as failed/resumable instead of leaving stale active progress.

### Changed

- Default batch size reduced to 20 text blocks to improve long-form provider reliability.
- Default provider retry count increased to 2.
- Provider prompts now explicitly require valid JSONL, exact row coverage, and preserved anchors.
- Latest job ordering now uses `last_active_at` so refresh binds to the most recent task.

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
