# Design: MENTORX

The locked system. Every Hallmark run reads this first and every screen shares it. Change it on
purpose; the file is the rule. Source of truth for values: `frontend/src/index.css` (`@theme`).

## System
- Genre: editorial (marketing page) · app screens for everything behind sign-in
- Shape of the first page: 05 Workbench (`frontend/src/pages/Landing.tsx`); app screens: a top bar shell
- Theme: brand (vibe: "calm navy study room, one periwinkle signal")
- Axes: navy/grotesque/periwinkle · posture: Restrained (the accent marks the primary action,
  the current selection and focus; nothing else)
- Audience: grade 4 to 8 students working on their own; calm and focused, few distractions

## Tokens
```css
@theme {
  --color-canvas: oklch(17.2% 0.032 269);   /* paper */
  --color-surface: oklch(21.3% 0.039 268);  --color-surface-2: oklch(24.7% 0.044 266);  --color-surface-3: oklch(28.5% 0.05 267);
  --color-line: oklch(31.8% 0.058 267);     --color-line-strong: oklch(38.3% 0.073 269);
  --color-ink: oklch(94.1% 0.014 273);      --color-ink-muted: oklch(78% 0.04 270);   --color-ink-faint: oklch(66% 0.045 270);
  --color-brand: oklch(69.1% 0.166 281);    --color-brand-ink: oklch(17.2% 0.032 269);  --color-focus: oklch(72% 0.19 281);
  --color-strength: oklch(77.3% 0.153 163); --color-developing: oklch(83.7% 0.164 84);
  --color-weakness: oklch(71.9% 0.169 13);  --color-unassessed: oklch(71.1% 0.035 257);
  --font-display: "Bricolage Grotesque Variable", ui-sans-serif, system-ui, sans-serif;  /* headings only */
  --font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;  /* everything else */
  --radius-card: 16px;  --radius-control: 12px;
}
```
No second accent hue (the old blue is gone: periwinkle beside blue is the purple-to-blue tell).
Status colours are fixed per diagnosis and only ever colour a status.

## Type
- Display face on page and section headings only; never on labels, buttons or data.
- App scale (1.2): 13 / 14 / 16 / 19 / 23 / 28px. Body 16px. Figures in tabular numerals.
- Labels, table heads and captions: the body face, one step smaller, sentence case, untracked.

## Controls
- Primary: periwinkle fill, dark ink text, 12px radius, 40px (44px on touch); one per screen.
- Secondary: 1px line-strong outline, same radius and height. Ghost: text only.
- Every control has hover, active, focus-visible (2px focus ring, instant) and disabled
  (opacity 0.55, `cursor: not-allowed`, the native attribute).

## Surfaces
- Ladder: whitespace, then a 1px hairline, then a surface well, then a card (border, no shadow).
- Never a card in a card, never a glow shadow, never a gradient fill.

## Shell
- Top bar: wordmark, Home / Skills / Progress (+ Admin), subject picker, account menu.
- Under 60rem the destinations move to a bottom tab bar (`Main (mobile)`).
- Practice and assessment use a narrow focused column (720px); other screens 1040px.

## Motion
- Character: still. Motion is state only (a hover colour step, a feedback panel arriving),
  `--dur-micro` 120ms / `--dur-short` 220ms; under reduced motion everything ends at once.

## Exports
`frontend/src/index.css` (`@theme`, Tailwind 4 utilities: `bg-surface`, `text-ink-muted`,
`border-line`, `bg-brand`, `font-display` ...). The landing page keeps its own scoped block
(`frontend/src/landing.css`) with the same values.
