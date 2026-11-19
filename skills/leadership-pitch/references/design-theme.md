# Design theme and slide-building rules

The look is calm, warm and executive: cream canvas, navy text, rust and teal accents, an elegant serif for headlines
and a clean sans for everything else. It reads as considered rather than "tech demo". If the user or their company
has a design system or house style, use that instead and keep only the structural rules below.

## Palette (hex, chosen once per deck)

| Role | Hex | Use |
|---|---|---|
| Cream (light background) | `#FBF9F4` | Most content slides |
| Tan (second background) | `#F3EBDD` | Alternate content slides, to give rhythm |
| Navy (dark) | `#1F2A37` | Headlines on light; background of cover, statement and closing slides |
| Rust (accent 1) | `#A24E16` | Eyebrow labels, "today / manual" side, warnings |
| Teal (accent 2) | `#1D4B4C` | "With data" side, positive states |
| Gold (accent on dark) | `#E3A66B` | Eyebrows and highlights on navy slides |
| Rust tint | `#F3DFCF` | Fill for "today" cells and callouts |
| Teal tint | `#DCEBE8` | Fill for "with data" cells; subtitle text on navy |
| Body grey | `#4B5563` | Card body text on white |
| Card | `#FFFFFF` with border `#E2D9C8` | Cards on cream or tan |

Rust and teal differ in lightness as well as hue, so the "today vs with data" contrast survives greyscale printing.

## Type

- Headlines: **Cormorant Garamond** 600 (60 to 64px on content slides, 120px on the cover), line-height 1.1.
- Everything else: **DM Sans** (400 body, 700 labels and card titles). Use DM Sans for big numbers too: the serif's
  old-style figures look wrong in stat tiles.
- Scale: 120 (cover) / 60-64 (headline) / 36-44 (statements, subtitles) / 26-28 (card titles, eyebrows) / 24 (body).
  Nothing under 24px, ever: it has to be readable from the back of a room.
- Eyebrows: 26px, 700, letter-spacing 3px, uppercase, rust on light, gold on navy.

## Slide kinds (reuse the same markup for the same kind)

- **Cover / closing (navy)**: eyebrow, huge serif title (width about 1400px), one-sentence subtitle in teal tint,
  a short gold rule and "[Your name] · [Team] · [Date]".
- **Statement**: eyebrow, headline, one large sentence or a simple from → to visual. For the core idea.
- **Card grid**: eyebrow, headline, 3 or 6 white cards with a 6px top border alternating teal and rust, a 28px
  bold title and 24px grey body. Optionally a dark band below with the takeaway line.
- **Comparison table**: grid rows of `300px 1fr 1fr`: process name on white, "today" on rust tint, "with data" on
  teal tint. The strongest slide in deck 1.
- **Step flow**: five boxes left to right with one line each (read, structure, extract, index, check).
- **Stack rows**: label column on navy with gold text, value column on white.
- **Ask**: navy slide with four phase cards (weeks, title, one line each) and the decision point last.

The heading always sits at the top margin in the same place; never centre the body vertically on some slides and
not others. Fill about 70% of the space; leave air.

## Building the decks (Slides artifact, or any 1920×1080 HTML slide format)

These rules come from building the originals as Claude Slides artifacts with inline styles:
- One `<section id="…">` per slide, 1920×1080 canvas, `padding:128px` for margins (content area 1664×824).
- **No `margin` anywhere** in an inline deck: space with the parent's `gap` and with padding wrappers.
- Flex and grid for layout; `width` on headings so they wrap where you want (headline width about 1500px).
- Speaker notes as plain text in one `<aside>`, the last child of the section: write the full talk track there.
- Slide ids are words, not reserved names (an id of `index` caused trouble; use `vectors`).
- Shorten a headline rather than leave one word orphaned on its last line.
- Fonts are declared once for the deck (Google Fonts: Cormorant Garamond 500-700, DM Sans 400/500/700).

## Checking

Run `scripts/check-overflow.js` from inside a deck folder (`node path/to/check-overflow.js`): it renders every slide
at 1920×1080 with Playwright and reports any content below y = 952 (the bottom margin). Fix every `OVER` by
splitting or trimming the slide; never shrink text below 24px to make it fit.

A complete example deck in this theme is in `assets/example-deck-idea/` (deck.json plus 11 slide files with speaker
notes). Start from it: copy, then rewrite the content for the new product. To publish it as a Claude Slides artifact,
the files go at `project/deck.json` and `project/slides/<id>.html` under one folder. The example is an inline-styled
deck (no `format` key); if the Slides type's own instructions ask a new deck for a shared stylesheet
(`project/deck.css`), follow them and move the repeated styles into classes there: the palette, type scale and slide
kinds above stay the same.
