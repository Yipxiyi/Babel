# Codex Workflow

## Decision

Use Babel as a CLI plus Codex orchestration. Do not make the core project a Codex plugin.

## Orchestrator Responsibilities

- Run `babel-epub prepare`.
- Review name candidates and create the global glossary.
- Maintain `translation_context.md`.
- Split work by batch or chapter.
- Give each worker the glossary, worker instructions, target batch, and relevant context.
- Require every worker to run `validate-batch`.
- Merge only validated outputs.
- Run `validate-batches`, `apply`, `audit`, output export checks, and final scans.

## Worker Contract

Each worker receives one or more JSONL batch files and must return matching `.translated.jsonl` files.

Workers must:

- Preserve row count and IDs.
- Write valid `translated_html`.
- Preserve root tags, IDs, classes, href/src links, anchors, images, and inline emphasis.
- Use the glossary exactly.
- Record uncertainties outside the EPUB.
- Run `validate-batch` before reporting completion.

Workers must not:

- Rename files.
- Change IDs or anchors.
- Flatten snippets to plain text.
- Add commentary inside the book.
- Use placeholder text.

## Parallel Dispatch

Parallel dispatch is safe when:

- Glossary decisions are stable enough for the dispatched range.
- Workers receive adjacent chapter context when pronouns, nicknames, or timeline continuity matter.
- The orchestrator reviews repaired or uncertain batches before global apply.

Parallel dispatch is unsafe when:

- A new character or term appears and has no glossary decision.
- The book depends heavily on unresolved aliases or hidden identity reveals.
- Workers are translating overlapping sections without a single merge owner.

## Final Gate

Before declaring success:

```bash
babel-epub validate-batches --pipeline-dir ./babel_work/book/pipeline
babel-epub apply --work-dir ./babel_work/book --output-book ./output_zh-CN.epub --output-format epub --title "Translated Title" --language zh-CN
babel-epub audit --epub ./babel_work/book/output.epub --out ./babel_work/book/pipeline/epub_audit.json
unzip -t ./babel_work/book/output.epub
```

Then scan the final book and EPUB intermediate for placeholder text and unexpectedly long untranslated passages. For non-EPUB final output, Calibre `ebook-convert` must be available during `apply`.
