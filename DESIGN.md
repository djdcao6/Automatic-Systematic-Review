---
# gstack: design-md-format=spec
name: Automatic Systematic Review
description: A calm, precise reading instrument for clinicians, with cool paper, ink-black controls, and AI shown in pencil while human decisions are set in ink.
colors:
  background: "#F4F5F7"
  surface: "#FFFFFF"
  text: "#151A23"
  text-muted: "#566070"
  border: "#D9DEE6"
  primary: "#1B2230"
  on-primary: "#FFFFFF"
  accent: "#2456D6"
  include: "#1E6F55"
  exclude: "#9B2C3A"
  maybe: "#8A5F08"
  ai-suggestion: "#646A78"
  background-dark: "#0F1218"
  surface-dark: "#171B23"
  text-dark: "#E7E9EE"
  text-muted-dark: "#98A0AE"
  border-dark: "#262C37"
  primary-dark: "#E7E9EE"
  on-primary-dark: "#0F1218"
  accent-dark: "#7FA0F5"
  include-dark: "#5CC0A0"
  exclude-dark: "#E5808B"
  maybe-dark: "#DDAF5C"
  ai-suggestion-dark: "#9AA1AF"
typography:
  display:
    fontFamily: Source Serif 4
    fontWeight: 500
    fontSize: clamp(2rem, 4vw, 3.25rem)
    lineHeight: 1.1
    letterSpacing: -0.02em
    fontFeature: opsz 48
  title:
    fontFamily: Source Serif 4
    fontWeight: 500
    fontSize: 1.625rem
    lineHeight: 1.2
    letterSpacing: -0.01em
    fontFeature: opsz 36
  reading:
    fontFamily: Source Serif 4
    fontWeight: 400
    fontSize: 1.0938rem
    lineHeight: 1.65
    fontFeature: opsz 14
  body:
    fontFamily: IBM Plex Sans
    fontWeight: 400
    fontSize: 0.9375rem
    lineHeight: 1.5
    fontFeature: tnum
  label:
    fontFamily: IBM Plex Sans
    fontWeight: 600
    fontSize: 0.6875rem
    letterSpacing: 0.08em
  mono:
    fontFamily: IBM Plex Mono
    fontWeight: 400
    fontSize: 0.8125rem
    fontFeature: tnum
rounded:
  sm: 2px
  md: 3px
  lg: 4px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
  2xl: 64px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
  button-primary-hover:
    backgroundColor: "#2A3446"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    borderColor: "{colors.border}"
    rounded: "{rounded.md}"
  input:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
  decision-stamp:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.include}"
    rounded: "{rounded.sm}"
  ai-annotation:
    borderColor: "{colors.ai-suggestion}"
    textColor: "{colors.ai-suggestion}"
    rounded: "{rounded.md}"
  keycap:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
    rounded: "{rounded.md}"
  table:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.border}"
  nav-link:
    textColor: "{colors.text-muted}"
---

# Automatic Systematic Review

## Overview

**Creative North Star:** A proof room, not a dashboard. Screening is reading, so the interface protects attention and makes one rule visible: the AI writes in pencil, the reviewer decides in ink.
**Product context:** A web app for clinicians and researchers running systematic reviews: PICO criteria, citation upload and deduplication, AI-assisted title/abstract screening, dual-reviewer conflicts, full-text extraction, PRISMA flow. Peers in the space are Covidence, Rayyan, DistillerSR and Otto-SR. The frontend is Next.js with Tailwind 4 and had no styling when this system was written.
**Mode per surface:**
- Screening, Conflicts, Duplicates, Extraction Fields: Operate.
- Abstract, criteria text, full text: Read.
- Login, register, pricing: Persuade, kept quiet and short.
- PRISMA flow export: Read, treated as a printed plate.

**Reference sites:** covidence.org, rayyan.ai, distillersr.com, ottosr.com (visited 2026-09-19).
**Key characteristics:**
- Cool paper ground with ink-black controls and no brand hue.
- Abstracts set in a 62ch serif column with PICO criteria in a sticky margin.
- Decisions carry color and a glyph. AI output is dashed and graphite.
- Hairline borders, 2 to 4px radii, almost no shadow.
- Tables appear only where columns must be compared.

## Colors

**Strategy:** Restrained. Ink and paper do most of the work, the blue accent is rare, and color is reserved for Include, Exclude and Maybe.
**Light or dark:** Light by default, since the use scene is a clinician at a desk for hours. Dark follows `prefers-color-scheme` and is a redesigned "lamplight" set, never a lightness inversion.
Named rules:
- `primary` (ink) carries every primary action. It flips to near-white in dark mode.
- `accent` carries links, focus rings and selection only. It is never used on buttons or decisions.
- `include`, `exclude` and `maybe` carry decisions and are always paired with their glyph (check, cross, tilde).
- `ai-suggestion` (graphite) carries anything the AI proposed. It is never filled and never a brand color.
- Neutrals are cool and tinted toward the ink hue. Pure black and pure white are not used as text or ground.
- Every text token clears 4.5:1 on `background` and `surface` in both themes.

## Typography

The type comes from the world of peer-reviewed journals and clinical data. Faces were verified on Google Fonts on 2026-09-19 and load through `next/font/google`, which self-hosts them with `display: swap` and no runtime request to Google.
- **Source Serif 4** is the reading and display voice, using the variable optical-size axis. Display and titles use the high optical sizes and reading text uses the low ones. It is used for abstracts, criteria text, project titles, page headings and the large PRISMA numerals. A serif holds up over hours of reading.
- **IBM Plex Sans** is the UI voice for labels, tables, forms and buttons, with tabular figures on. It is on the overused-as-display list, and is used here only as body and UI on Operate surfaces, where its legibility at small sizes is the point.
- **IBM Plex Mono** carries DOIs, PMIDs, citation IDs, keycaps and extraction values.

Scale: display, title and reading differ by size and by family, not only by weight. Label is small uppercase Plex Sans for section headings in margins and table headers. Reading text is capped at 62ch and never runs full width.

## Layout

App shell: a 200px left project rail, then the main area. Screening uses a folio strip ("412 of 1,860" with a thin progress line), a reading page with a 62ch column, and a 240px sticky margin for PICO criteria and the AI suggestion. On narrow screens the rail collapses to a header with a Menu button that reveals the same links, so navigation stays reachable, and the margin drops below the page. Spacing follows a 4px base with a large step between sections (40px and 64px) and a small step inside components (4px to 16px). Density is compact in queues and tables and generous on the reading page. The grid breaks on purpose in one place: the sealed co-reviewer tab, which sits in the margin until the reviewer commits.

## Elevation & Depth

Depth comes from borders and surface tints. Panels sit on `surface` over the `background` ground with a 1px `border`. The only shadow is a soft offset shadow on framed mockups and modal layers (`0 6px 18px -10px` at low alpha). No zero-offset glows, no halos, no backdrop blur as a default surface.

## Shapes

Radii are small: 2px for stamps and chips, 3px for buttons, inputs and keycaps, 4px for rare large containers. Nested elements use the outer radius minus the gap. Nothing is pill-shaped except a possible count badge.

## Components

- **button-primary:** ink fill, on-primary text. Hover lightens the fill slightly. Focus-visible uses a 2px `accent` ring with a 2px offset. Disabled drops to 45% opacity and loses the hover.
- **button-secondary:** surface fill with a hairline border. Hover darkens the border to `text-muted`.
- **input:** surface fill, hairline border. Focus shows an `accent` ring. Error text uses `exclude` and always pairs with the glyph and a message.
- **decision-stamp:** the reviewer's recorded decision. Solid 1.5px border in the decision color, glyph at left, full contrast, settles in over 120ms. It is the only place a decision color fills an edge.
- **ai-annotation:** 1px dashed `ai-suggestion` border, lighter weight, labelled "AI suggestion (advisory)". It never uses a filled background or a decision-colored border.
- **keycap:** mono text with a 2px bottom border, used for I, E and M. Every keyboard action shows its key.
- **table:** used for Conflicts, Duplicates and Extraction only. Uppercase label headers, hairline row rules, no zebra striping.
- **nav-link:** muted text that moves to `text` on hover. The current item gets a `background` fill and medium weight, not a colored edge.

What never changes: decisions always carry a glyph, AI output is always dashed, and reading text is always serif.

## Do's and Don'ts

- Do: show AI output dashed and graphite and human decisions solid and inked.
- Do: pair every decision color with its glyph so color is never the only carrier.
- Do: cap reading text at 62ch in Source Serif 4.
- Do: show empty, loading, error and long-content states for every list and panel, using plain text and no illustration.
- Do: withhold the AI suggestion and the co-reviewer's decision in blind mode until the reviewer commits.
- Don't: give the AI a confident filled badge, a brand color or a sparkle icon.
- Don't: use gradients, gradient text, glows, icons in circles, or cards inside cards.
- Don't: build the screening screen as a spreadsheet row.
- Don't: add a stats row of big numbers, a logo strip, or stock photography to Persuade surfaces.
- Don't: use the words "seamless", "effortless" or "supercharge" in the interface copy.

## Motion

- **Approach:** minimal-functional
- **Easing:** enter(ease-out) exit(ease-in) move(ease-in-out)
- **Duration:** micro(50-100ms) short(150-250ms) medium(250-400ms) long(400-700ms)
- **The one authored moment:** a decision stamp settling into the margin over 120ms with a 3px drop, disabled under `prefers-reduced-motion`.

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-09-19 | Initial design system created | Created by /design-consultation after visiting Covidence, Rayyan, DistillerSR and Otto-SR, plus an independent Claude subagent proposal. Codex was unavailable, so outside input is single-model. |
| 2026-09-19 | Cool paper ground instead of warm cream | Cream plus serif is the most common AI-generated look, and Otto-SR already holds the serif and green lane. |
| 2026-09-19 | Light graphite and ochre darkened to `#646A78` and `#8A5F08` | The first values missed 4.5:1 on the paper ground. |
| 2026-09-19 | AI shown in pencil, decisions in ink | The category sells speed with a confident AI. Reviewers must defend their evidence chain, and CONTEXT.md already keeps the AI Suggestion apart from the Screening Decision. |
| 2026-09-19 | Approved from an HTML preview, not AI mockups | The gstack designer needs an OpenAI API key that is not configured on this machine. |
| 2026-09-19 | Screening folio: the count is the citation's place in the list, the progress line is the share of active citations that already have a decision | Place in the list is not progress, and a reviewer who skips around would see a misleading bar. The list order is `created_at`, then `id`, and the backend reports the place on the citation detail so the page never downloads the whole list. |
| 2026-09-19 | I, E and M select a decision, and Ctrl+Enter or the button records it | Recording stays an explicit act, as with the radios. A keystroke that saved immediately would make a mis-press a recorded decision in a blind review. |
| 2026-09-19 | No screening decision is pre-selected, and saving without a choice asks for one | The page used to open with Maybe selected. With a Ctrl+Enter shortcut, one stray keystroke could record it. The full-text decision form still defaults to Maybe, since it has no shortcuts. |
| 2026-09-19 | Keycaps and the shortcut hint are hidden on touch devices (`hover: none`) | There is no keyboard to press. Choices and the Previous and Next links grow to 44px tall on narrow screens instead. |
| 2026-09-19 | The sealed Co-Reviewer tab shows while a reviewer is blind in a Dual review, and hangs 1.25rem past the margin column | It tells the reviewer a second opinion exists without leaking it. It is the one place the grid breaks on purpose. The overhang stays under the page gutter, so it never causes horizontal scroll, and it stops hanging when the margin drops below the page. |
| 2026-09-19 | Empty states are one plain muted sentence that says what is empty and where to add it, shown only after a successful load. Loading and error states sit inside `main` | Follows the Do's and Don'ts. An empty list before the first response is not "nothing there", and an empty message next to a load error would be wrong. |
| 2026-09-19 | The 200px project rail is not built in the app yet | The app has no separate routes for Criteria, Search terms, Conflicts and the rest, so a rail has nothing to link to. In the standalone preview the rail collapsed to a Menu button on narrow screens instead of hiding, so navigation stayed reachable. The Layout section still says the rail hides. |
| 2026-09-19 | The PRISMA PNG export is always the light plate, with the web fonts embedded, whatever theme the viewer is in | The export is a printed plate that goes into a manuscript or a slide, so it should not depend on the viewer's dark mode. The tokens live in `LIGHT_TOKENS` in `png-export.ts`, and a test fails if they drift from the light `:root` in `globals.css`. |
| 2026-09-19 | Pretext is not used in the app | It only paid off in the standalone preview, where every abstract was on the page and could be measured to reserve one height. In the app each citation is its own route, and the project can hold thousands. |
