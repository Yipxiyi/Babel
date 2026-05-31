# Babel PRD

## Background

EPUB translation is easy to do badly: many scripts flatten books into plain text, losing CSS, links, anchors, images, table of contents behavior, and typographic emphasis. Babel exists to make high-quality, structure-preserving translation workflows repeatable.

## Audience

- Readers translating legally owned EPUBs for personal use.
- Translators who want chapter/batch workflows without destroying EPUB layout.
- Agent users who want a main orchestrator plus parallel batch workers.
- Developers building reviewable EPUB translation automation.

## Goals

- Preserve EPUB structure and formatting as much as possible.
- Extract human-readable XHTML content into stable JSONL batches.
- Support global glossary and context continuity across batches.
- Validate translated snippets before applying them.
- Rebuild a standards-compatible EPUB.
- Keep the core dependency-free and model-agnostic.

## Non-goals

- Babel does not provide translation rights.
- Babel does not bundle a translation model.
- Babel does not upload books to third-party services.
- Babel does not try to be a complete EPUB editor.
- Babel does not hardcode one book, language pair, or provider.

## Functional Requirements

- `prepare` unpacks an EPUB, locates OPF/spine content, extracts translatable XHTML blocks, writes batches, creates name candidates, and creates worker instructions.
- `validate-batch` verifies row IDs, root tags, structural attributes, links, anchors, and placeholder patterns.
- `validate-batches` blocks apply when any translated batch is missing or invalid.
- `apply` replaces only validated XHTML snippets and packages an EPUB with `mimetype` first and uncompressed.
- `audit` checks manifest presence, spine XHTML count, internal links, anchors, images, and ZIP integrity.
- `report` writes a compact translation report.

## AI And Agent Requirements

- The main agent owns glossary decisions and context ledger updates.
- Batch workers must not invent IDs, change root tags, or alter structural attributes.
- Workers must validate their output before handing it back.
- Parallelism is allowed only where batches are independent and the glossary/context contract is stable.

## Security And Privacy

- Private EPUBs and translated outputs must be excluded from git by default.
- Babel should not make network requests in core commands.
- Babel should avoid provider-specific credentials in core code.

## Success Metrics

- A minimal EPUB can round-trip through prepare, validate, apply, and audit.
- Broken internal links and missing anchors are detected.
- Placeholder/filler translations are rejected before packaging.
- New users can run the quick start without reading source code.

## Open Questions

- Whether to add optional EPUB 3 navigation document translation support beyond body extraction.
- Whether to provide optional provider adapters in a separate package.
- Whether to ship a Codex skill template as an optional companion artifact.
