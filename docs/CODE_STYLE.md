# Code Style

## Python

- Python 3.11+.
- Standard library first.
- Keep CLI behavior explicit and testable.
- Prefer small pure functions around EPUB parsing, validation, and packaging.
- Raise clear exceptions for invalid EPUB structure or invalid translation batches.

## XML And EPUB

- Preserve namespaces where possible.
- Never flatten EPUB content to plain text.
- Treat IDs, href/src links, anchors, image references, and CSS classes as structural data.
- Package `mimetype` first and uncompressed.

## Tests

- Use stdlib `unittest`.
- Generate miniature EPUB fixtures in tests instead of committing book files.
- Add regression tests for every validation rule that prevents known corruption.
