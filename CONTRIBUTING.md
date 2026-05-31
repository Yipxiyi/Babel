# Contributing

Contributions are welcome when they preserve Babel's core promise: structure-preserving EPUB translation with strict validation.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Pull Request Checklist

- Keep generated ebook outputs, JSONL batches, and private book content out of commits.
- Add tests for CLI behavior, validation rules, or EPUB packaging changes.
- Update `README.md` when user-facing commands change.
- Update `docs/ARCHITECTURE.md` when pipeline boundaries change.
- Update `CHANGELOG.md` for user-visible changes.

## Scope Guidance

Babel should stay a small, reliable CLI. Avoid adding provider-specific translation API calls to the core package. If provider adapters are added later, keep them optional and isolated.
