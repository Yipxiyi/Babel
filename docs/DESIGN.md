# Design

## Scope

Babel has a product UI served by `babel-server` from the React/Vite build in `src/babel_epub/static/`. Design guidance applies to the Web app, public assets, diagrams, and README visuals.

## Visual Direction

- Minimal editorial utility with a structured workbench layout.
- Warm paper background, ink type, clay primary action, deep green terminal, and a restrained amber/blue-green glow from the project icon.
- Geometric blocks, tower forms, and terminal process feedback.
- Avoid generic purple AI gradients.

## Tokens

- Paper: `oklch(95.7% 0.025 78)`
- Surface: `oklch(98.4% 0.016 75)`
- Ink: `oklch(19.5% 0.027 72)`
- Clay: `oklch(57% 0.143 44)`
- Terminal: `oklch(15.5% 0.045 142)`
- Info light: `oklch(56% 0.105 207)`

## Product UI

- Use a three-column asymmetric workbench on desktop: input/settings, glossary/progress, output/validation.
- Collapse to one column on mobile.
- Keep form labels above controls and preserve visible focus states.
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
