# Spec 0001: EPUB Translation Pipeline

## Objective

Provide a repeatable CLI workflow for translating EPUB content while preserving structure and packaging validity.

## Acceptance Criteria

- A valid EPUB can be unpacked into a private work directory.
- XHTML body blocks are extracted into JSONL with stable IDs.
- Batches can be translated independently.
- Invalid translated snippets are rejected.
- Placeholder/filler translations are rejected.
- Valid batches can be applied back into the EPUB tree.
- Output EPUB passes ZIP integrity and structural audit.
- Tests cover a minimal round trip and placeholder rejection.

## Current Implementation

- Package: `src/babel_epub`
- CLI: `babel-epub`
- Tests: `tests/test_pipeline.py`
