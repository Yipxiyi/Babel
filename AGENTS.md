# Babel Agent Guide

## Source Of Truth

- Product intent: `docs/PRD.md`
- Architecture: `docs/ARCHITECTURE.md`
- Batch orchestration: `docs/CODEX_WORKFLOW.md`
- Brand and public voice: `docs/BRAND.md`
- Design and asset rules: `docs/DESIGN.md`
- Public usage: `README.md`

## Working Rules

- Keep Babel dependency-free unless a feature cannot be implemented safely with the standard library.
- Do not commit EPUB books, translated EPUBs, generated JSONL batches, local workspaces, or user reading material.
- Preserve EPUB structure first: spine, manifest, CSS, images, IDs, anchors, links, and XHTML root tags are not optional.
- Prefer explicit validation gates over best-effort repair.
- Keep the CLI model-agnostic. Agent/Codex orchestration belongs in docs and worker instructions, not hardcoded API calls.
- Use `apply_patch` for manual edits in Codex sessions.

## Validation

Run before claiming changes are complete:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile src/babel_epub/*.py
```

For EPUB behavior changes, add or update a minimal fixture-generating test in `tests/`.

## Release Notes

Update `CHANGELOG.md` for user-visible CLI, validation, packaging, or documentation changes.
