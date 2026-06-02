# Product

## Register

product

## Users

Babel is used by technically capable readers, translators, researchers, and agent operators who need to translate long-form ebooks while preserving chapter structure, glossary consistency, links, images, and output format. They may run it locally through Docker, from source, Codex, or Claude MCP, and they usually care more about control and recoverability than one-click automation.

## Product Purpose

Babel turns an ebook into a structured, validated translation job. It normalizes supported formats into an EPUB workspace, builds glossary and batch context, sends batches to a user-configured provider, records progress events, supports failure recovery, and exports the final book in the selected format. Success means the user can understand what is happening, intervene before wasting tokens, resume after provider failures, and download validated artifacts.

## Brand Personality

Careful, architectural, calm. Babel should feel like a translation workbench, not a magic button. The interface should communicate structure preservation, checkpoints, and traceability.

## Anti-references

Avoid generic AI SaaS dashboards, purple or neon gradients, chat-first layouts, magical claims, decorative cards without function, and optimistic progress screens that hide failures. Avoid anything that implies perfect translation, copyright bypassing, or unattended public hosting.

## Design Principles

- Preserve structure visibly: the UI should make batches, glossary, validation, and output artifacts legible.
- Keep control local: provider settings and keys are entered per run and the interface should make that boundary clear.
- Recovery is a first-class path: failed jobs need clear state, event history, failed batch context, and resume affordances.
- Reduce first-run uncertainty: guide the user through upload, prepare, review, provider setup, start, monitor, and download.
- Let process be felt: progress should include a terminal-like event stream, not just a static bar.

## Accessibility & Inclusion

Target WCAG AA contrast, keyboard-operable forms and dialogs, visible focus states, reduced-motion alternatives, no color-only status communication, and bilingual English/Simplified Chinese UI copy. Motion should be short, stateful, and non-blocking.
