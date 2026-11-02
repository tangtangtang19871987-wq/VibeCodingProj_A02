---
name: html-ppt-studio
description: Build professional, presentable HTML slide decks with 24 themes, 31 layouts and 25+ animations. Use when the user asks for a presentation, slide deck, pitch, keynote-style talk or "PPT" delivered as HTML — or wants to restyle/re-theme an existing HTML deck. Zero dependencies; output is a single static .html file that presents in any browser and prints to PDF.
---

# HTML PPT Studio

A dependency-free toolkit: 1920×1080 slides that auto-scale to any screen, themed by CSS variables, laid out by named layouts, animated by `data-anim` attributes, driven by a small keyboard/touch runtime.

```
assets/            base.css · layouts.css · animations.css · themes.all.css · themes/*.css · runtime.js
templates/layouts/ 31 ready-to-edit <section> snippets + layouts.json
scripts/new_deck.py  assembles a deck from layout names
reference/         layouts.md · themes.md · animations.md
examples/          demo-all-layouts.html (every layout; press T to flip themes)
```

## Workflow

1. **Clarify** only what you can't infer: topic, audience, length, tone. Default 8–12 slides.
2. **Outline** one message per slide (the headline is the takeaway, not a topic label). Open with `cover`, end with `closing`; use `section` to break up 10+ slide decks.
3. **Pick layouts** from `reference/layouts.md` — match the content shape (numbers → `kpi-row`/`big-number`/`bar-chart`; sequence → `timeline`/`process`/`roadmap`; contrast → `comparison`/`pros-cons`). Vary layouts; don't use `bullets` more than 2–3 times.
4. **Pick a theme** from `reference/themes.md` (see guide below).
5. **Scaffold**: `python3 scripts/new_deck.py --out deck/index.html --theme aurora --title "…" --layouts cover,agenda,bullets,kpi-row,closing`
   Add `--inline` for a single self-contained file to hand over. `--list` prints all layouts, themes and animations.
6. **Replace placeholder content** by editing the generated HTML (keep the classes). Write real speaker notes in each section's `data-notes="…"`. Or write your own `<section>`s using the snippets as models and pass `--slides-file`.
7. **Verify visually**: open in headless Chromium (Playwright), screenshot each slide at 1280×720 after ~2.5 s (animations settle), and check for overflow/clipping. Fix text that exceeds its box by shortening copy — don't shrink fonts below ~26px.

## Authoring rules

- A slide is `<section class="slide layout-NAME" data-notes="…">…</section>` inside `<main class="deck" data-transition="fade|slide|zoom|none">`.
- Stage is 1920×1080 px; use px, never vw/vh. Safe padding is 96px/120px.
- **Content budget**: headline ≤ 10 words; ≤ 5 bullets; ≤ 30 words per card; one idea per slide.
- Never hard-code colors — use `var(--accent)`, `var(--accent2)`, `var(--fg)`, `var(--muted)`, `var(--card)`, `var(--border)`, `var(--bg)` so every theme works. Status colors: `--good`, `--bad`, `--warn`.
- Images: `<div class="img-ph" data-label="…"><img src="x.jpg" alt="…"></div>` (the placeholder gradient shows until an image is supplied). Use real files/URLs the user provided; never invent sources.
- Set the theme with `<body data-theme="NAME">`. Add `data-theme-locked` to `<body>` to stop the runtime restoring a viewer's previously chosen theme.

## Animations (`data-anim="NAME"`)

Add `style="--d:.3s;--t:.8s"` for delay/duration. Replays each time a slide appears. Put `data-anim-stagger="fade-up"` (optional `data-stagger=".15"`) on a parent to animate children in sequence. Numbers count up with `data-anim="count-up" data-count="4.2" data-prefix="$" data-suffix="M"`.

- Entrances: `fade-in fade-up fade-down fade-left fade-right zoom-in zoom-out flip-x flip-y rotate-in bounce-in blur-in slide-up-big`
- Reveals: `wipe-right wipe-up typewriter draw-line grow-x`
- Emphasis/loops: `pulse float shake glow spin gradient-shift`
- Other: `count-up stagger-pop`

Use 1–2 animation styles per deck for consistency; reserve loops (`float`, `pulse`, `glow`) for a single hero element.

## Theme guide

| Situation | Try |
|---|---|
| Tech / product launch | `aurora`, `midnight`, `glass`, `neon-cyber` |
| Corporate / finance | `corporate-blue`, `mono-light`, `swiss`, `solarized-light` |
| Editorial / storytelling | `paper`, `coffee`, `rose`, `gold-luxe` |
| Developer talk | `dracula`, `nord`, `terminal-green`, `solarized-dark` |
| Bold / creative | `brutalist`, `retro-80s`, `sunset`, `lavender` |
| Nature / health / sustainability | `forest`, `ocean`, `mint` |

Projector in a bright room → prefer a light theme. Add a custom theme by copying `assets/themes/aurora.css`, renaming the selector, and appending it to `assets/themes.all.css`.

## Presenting (runtime keys)

`←/→/Space` navigate · `Home/End` · `F` fullscreen · `O` overview · `T`/`Shift+T` next/prev theme · `N` speaker notes · `?` help · swipe on touch · `#7` deep-links slide 7. **Print to PDF**: browser Print → "Save as PDF", background graphics on (page size is set to 1920×1080 automatically).

## Adding a layout

Add `.layout-NAME{…}` to `assets/layouts.css` (style via theme variables only), drop a snippet in `templates/layouts/NN-name.html`, and register it in `layouts.json`.
