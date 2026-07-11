# Design

## Scope

Babel has a product UI served by `babel-server` from the React/Vite build in `src/babel_epub/static/`. Design guidance applies to the Web app, public assets, diagrams, and README visuals.

## Visual Direction

- Minimal editorial utility with a structured workbench layout.
- HeroUI-native product workbench: use HeroUI semantic surfaces, controls, focus rings, radii, shadows, and component variants as the visual source of truth.
- Babel may keep a restrained local accent through HeroUI `--accent` and `--accent-soft` tokens, but components must not reintroduce the old `paper / ink / clay` design language in JSX or ad hoc CSS utilities.
- The terminal event stream is the only product-specific surface with custom visual tokens, because it communicates long-running translation process state.
- Geometric blocks, tower forms, and terminal process feedback.
- Avoid generic purple AI gradients.

## Tokens

- Use HeroUI v3 CSS variables directly:
  - `--background`, `--foreground`
  - `--surface`, `--surface-secondary`, `--surface-tertiary`
  - `--default`, `--default-hover`
  - `--accent`, `--accent-foreground`, `--accent-soft`
  - `--success`, `--success-soft`
  - `--warning`, `--warning-soft`
  - `--danger`, `--danger-soft`
  - `--border`, `--separator`, `--focus`
  - `--surface-shadow`, `--overlay-shadow`, `--field-shadow`
- Use HeroUI component variants instead of component-local color recipes:
  - Buttons: `primary`, `secondary`, `ghost`, `outline`, `danger`, `danger-soft`
  - Cards: `default`, `secondary`, `tertiary`, `transparent`
  - Inputs and selects: `primary`, `secondary`
  - Chips: `soft` with `accent`, `success`, `warning`, `danger`, or `default`
  - Progress bars: `accent`, `success`, `warning`, `danger`, or `default`
- Do not add new Tailwind theme tokens named after the old visual language (`paper`, `ink`, `clay`) or style components with one-off `bg-*`, `border-*`, `shadow-*`, and `rounded-*` recipes when a HeroUI variant/token exists.

## Product UI

- Use a three-column asymmetric workbench on desktop: input/settings, glossary/progress, output/validation.
- Collapse to one column on mobile.
- Keep form labels above controls and preserve visible focus states.
- Prefer HeroUI components for buttons, cards, modals, inputs, selects, switches, tables, chips, close buttons, and progress bars.
- Layout classes may control grid, width, spacing, sticky positioning, and responsive behavior; component skinning should come from HeroUI variants and CSS variables.
- Job progress needs both percentage and event stream, because long translation jobs need activity perception.
- Running jobs must show active batch count and failed batch count.
- Failed jobs must show failed batch lists and resume action without hiding the event history.

## Asset Rules

- Keep source assets in `docs/assets/brand/`.
- Prefer SVG for logos/icons.
- Use `docs/assets/brand/babel-icon.png` as the primary project icon.
- Do not embed extra generated raster art unless it adds concrete value.
- README imagery should load from repo-relative paths.

## Accessibility

- Icons need `title` and `desc` when SVG is inline or directly referenced.
- Diagrams should be understandable from surrounding text.
- Do not use color alone to convey command state or validation outcome.
