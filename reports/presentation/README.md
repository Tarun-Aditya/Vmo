# Leadership presentation

Everything used to pitch the idea to leadership: four slide decks, a click-through page that shows
contracts turning into relational data, the invitation email, and the order to present them in.

The idea in one line: **a data pipeline that turns unstructured documents into structured, linked
data, applied at scale to the supplier contracts behind hotel operations and property managers.**
The product is the proof that the data can run the business; the presentation explains the idea
first.

## What is here

| Piece | Published link | Source in this folder |
|---|---|---|
| Complete deck (all three below, 36 slides) | https://claude.ai/artifact/NryKpp2rHXGscnf77iC9zt | `decks/complete/` |
| Deck 1: the idea, *From Documents to Decisions* (11 slides) | https://claude.ai/artifact/PngoNAAhoKfyQjwtHGeLzG | `decks/1-idea/` |
| Deck 2: hotel operations, *From Hotel Contracts to Hotel Operations* (12 slides) | https://claude.ai/artifact/5PHKNWmEZHYSio2vjNCrLM | `decks/2-hotel-operations/` |
| Deck 3: *Solution and Architecture* (13 slides) | https://claude.ai/artifact/Fq9jvutjv13tFRwMgrtf1j | `decks/3-architecture/` |
| *From paper to rows* (presenter page) | https://claude.ai/artifact/KNfuZFnyyYj5gUV8Mboqci | `paper-to-rows.html` |
| Invitation email | | `email.md` |

The links are private to their owner. Share each one from its page's Share menu before anyone else
opens it.

Other files:

- `paper-to-rows.local.html`: the same page wrapped as a complete HTML file, to open from disk in
  a browser with no network other than Google Fonts (it falls back to system fonts offline).
- `paper-to-rows-data.json`: the data embedded in the page, as exported by
  `scripts/export_presentation_data.py`.
- `decks/check-overflow.js`: renders each slide of a deck with Playwright and reports any content
  below the bottom margin (y 952). Run it from inside a deck folder: `node ../check-overflow.js`.
- `screenshot-*.png`: the page's live runs and document view.
- `video/paper-to-rows-demo.mp4`: the demo recorded as one video (2 min 40 s): the page's one-document and ten-document
  stories with documents opened, then the product on the same rows (Renewals, the repository, Ask). One screenshot per
  step and `video/report.md` (17/17 steps). Re-record with `make presentation-video` (app running in Demo mode with the
  sample folder read, `SIMULATORS=1`).

## Order of the session (about 35 minutes)

1. **Deck 1, the idea (10 minutes).** The business runs on contracts; their terms are locked in
   documents; every process around them is manual. AI turns documents into structured, related
   data, continuously, and every process then runs on the data.
2. **Deck 2, hotel operations (8 minutes).** The same problem for a hotel group: what it means for
   the property manager at one hotel, and for an owner across many.
3. **From paper to rows (8 minutes).** The missing piece between the idea and the product: one
   document, then a folder of ten, turning into rows. Talk track below.
4. **The product (5 minutes).** Switch to the running app: renewals, the contract repository and
   Ask, all reading the rows the page just showed. See `DEMO.md` act 3.
5. **Deck 3, architecture (as needed).** For a technical audience, or for questions afterwards.

The complete deck has all three decks in this order, each starting with its own cover, so one
link covers steps 1, 2 and 5.

## From paper to rows: talk track

Walk through with Next/Back or the arrow keys; press `1` or `2` to jump between the two stories.
Each step has its own address (`#one1` to `#one6`, `#ten1` to `#ten5`).

**One document** (the waste contract for the Airport Inn)

1. *A signed contract is a PDF only a person can read.* Five pages. The answers the business needs
   are in it, and the row we want is empty.
2. *Watch it run.* Starts on arrival; "Run again" replays it (about 12 seconds). Read reveals the
   pages; Structure outlines 20 typed clauses; Extract highlights each value in its sentence as its
   row appears; Index counts the vectors; Check lists the failures. "Stored as contract #62."
3. *Clauses.* The same document, clauses outlined, and the `clauses` rows beside it.
4. *Terms with their source.* Click any value and the page scrolls to the words it came from.
5. *Rows.* The `contracts` row, `field_extractions`, `obligations` and `check_results`, joined by
   keys.
6. *What the rows say.* Expiry minus notice: the last day to act was 1 September 2026, already
   passed. The contract renews for 36 months with no liability cap and no exit.

**Ten documents**

1. *A real folder.* Eleven files: PDF, Word, a scanned amendment and a renamed copy. Click any file
   to open it.
2. *The same pipeline, file after file.* Starts on arrival (about 12 seconds). The "Reading now"
   panel shows each file's step, its clause types and its first values; the scan shows OCR; the
   copy is recognised by its fingerprint and not stored. The contracts table fills row by row.
   Suggested move: open `meridian_amendment_1_scan.pdf` to show that a scanned image became
   searchable text with values.
3. *Connected.* The schedules and NDA link to their master agreement; the scanned amendment
   changes payment from 45 to 30 days and moves the end date; the effective terms show which
   document each value comes from.
4. *The business on the rows.* Four questions, each one query: where we must act, where liability
   is unlimited, which contracts we cannot leave, spend by hotel.
5. *And the product.* The same rows feed renewals, Ask, checks and redline, obligations, effective
   terms and spend. "Now let me show you the product running on this data."

**Document view.** Click any file, any row of the contracts table, or any box in the master
agreement diagram. It shows the text as the pipeline read it, split into typed clauses with page
markers; extracted values are highlighted and source clauses outlined. Click a value on the right
to jump to its passage. `Esc` closes it.

## What is real on the page, and what to be ready for

- Every contract, clause, value, confidence and query result comes from the database after the
  pipeline read the sample folder (`data/realistic_hotel/`) with the offline engine. Nothing was
  typed in. The contracts and companies are fictional.
- Some values have no exact quote to highlight (true/false, "2 times annual fees"); those point to
  their clause, or say "judged from the whole text" when no single clause holds them. About 60% of
  values are highlighted (6 to 11 per document).
- The waste contract's annual value is empty because the pipeline did not extract it.
- The document view shows the text as read, not the PDF layout; for the scan that is the OCR text.
- The live runs are animations of the recorded results, timed for the audience; the real pipeline
  takes a few seconds per document offline. With Claude switched on, speed and accuracy on our own
  contracts have not been measured yet.
- "Agentic": the reading runs as a fixed sequence of steps. What makes the system agentic is that
  it works on its own (watches for files, reads, links, checks and raises what needs action), and
  the Ask assistant decides for itself whether to query the database, search clauses, or both.

## Updating

**The page.** Edit `paper-to-rows.html` and publish it to the same link with the Artifact tool
(same artifact URL). If the sample data changes:

1. Load the hotel database and read the sample folder (`DEMO.md`, "Before you start").
2. `python scripts/export_presentation_data.py > reports/presentation/paper-to-rows-data.json`
3. Paste that JSON into the `<script type="application/json" id="docs-data">` block, with `</`
   written as `<\/`.
4. If the contract ids are no longer 53 to 62, update `FOLDER`, `ROWS`, `WASTE_FIELDS`,
   `WASTE_OBLIGATIONS` and `WASTE_FAILS` at the top of the page's script, and the `#62` text.
5. Rebuild `paper-to-rows.local.html` by wrapping the page in `<!doctype html><html><head>` with a
   charset and viewport meta, and `<body>`.

**The decks.** Each deck folder is the source of a Slides artifact: `project/deck.json` holds the
title, slide order and sections, and `project/slides/<id>.html` one slide each, with speaker notes
in its `<aside>`. Slides use inline styles (the decks have no `format` key), padding instead of
margins, and text no smaller than 24px. Publish a changed slide to the deck's link with the
Artifact tool, then run `check-overflow.js`. The complete deck's slide ids carry a prefix per part
(`a-` idea, `b-` hotel operations, `c-` architecture); a change to one of the three decks has to be
copied into it.

Look: cream `#FBF9F4` and tan `#F3EBDD` backgrounds, navy `#1F2A37`, rust `#A24E16`, teal
`#1D4B4C`, gold `#E3A66B`; Cormorant Garamond headings, DM Sans text.
