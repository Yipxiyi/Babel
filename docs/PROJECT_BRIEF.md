# Project Brief

Babel is an open-source, dependency-free Python CLI/Web tool for layout-preserving ebook translation workflows.

It extracts translatable XHTML blocks into JSONL batches, lets humans or agents translate those batches with a shared glossary/context ledger, validates translated snippets, applies them back to the EPUB tree, and audits the final EPUB.

The project is intentionally model-agnostic. Codex/subagents are a recommended orchestration mode, not a runtime dependency.
