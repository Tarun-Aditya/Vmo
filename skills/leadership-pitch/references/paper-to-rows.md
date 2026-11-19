# The "paper to rows" page

A standalone, presenter-driven web page shown between the idea decks and the product. It makes the core mechanism
visible: unstructured input (documents) becoming structured, related data, first for one input, then for many, and
then that data answering business questions. Example: `assets/paper-to-rows-example.html` (the original, with its
data embedded; open it in a browser to see it work).

## Contents
1. Story structure
2. Interactions
3. The data it needs
4. Adapting it to another product
5. Building and publishing
6. Pitfalls found in the original

## 1. Story structure

Two stories, switched by tabs, walked with Next/Back or arrow keys (`1` / `2` jump between stories; each step has a
hash address like `#one3` so a step can be linked).

**One document (6 steps)**: use the input with the best "aha" (the original: a waste contract whose renewal notice
window had already closed).
1. *The input as people see it today*: the document beside the empty row we want ("only a person can read it").
2. *Watch it run*: an animated run. A five-stage tracker (Read, Structure, Extract, Index, Check) lights up; the
   document is revealed page by page; parts are outlined and typed one by one; each value is highlighted in its
   sentence as its row is added to a table; counters climb; failed checks appear; "Stored as #62".
3. *Structure*: the parts (clauses) outlined with their types, and the parts table.
4. *Values with their source*: value chips with confidence, clause and page; clicking one scrolls to its words.
5. *Rows*: the main record, the per-value rows pointing back to their source, and derived rows (duties, checks),
   joined by keys.
6. *What the rows say*: the business answer the input was hiding, with the one line of SQL that finds it.

**Many documents (5 steps)**: about ten files, deliberately messy.
1. *A real folder*: mixed formats (PDF, Word), a scanned image, files that belong together, and an exact copy under
   another name.
2. *The same pipeline, file after file*: an animated run with a "Reading now" panel (current file, stage, part types
   appearing, first values found; the scan shows OCR; the copy shows "same fingerprint, not stored"), stat tiles,
   and the main table filling row by row.
3. *Connected*: the related files linked to their parent; an amendment changing two terms, shown as old value struck
   through, new value, and the source document; the duplicate turned away.
4. *The business runs on the rows*: four questions, each with its SQL and result table (where must we act, where are
   we exposed, what can't we leave, what do we spend by site).
5. *And the product*: six cards naming the product's screens and the tables behind them, ending with "Now let me
   show you the product running on this data."

## 2. Interactions

- **Run / Run again** on both run steps; runs start automatically when the step opens. Respect
  `prefers-reduced-motion` by jumping straight to the end state.
- **Document view**: clicking any file, any row of the main table, or any box in the relationship diagram opens a
  side sheet: the text as the pipeline read it, split into typed parts with page markers, extracted values
  highlighted where they occur, source parts outlined; on the right, the value chips; clicking a chip scrolls to its
  passage. Esc closes it. The duplicate opens its original with a banner explaining it was not stored again.
- Theme tokens for light and dark; works at phone width; no external requests beyond Google Fonts.

## 3. The data it needs

Export it from the product's database with a script (the original: `scripts/export_presentation_data.py`) and
embed it as JSON. Never type values in by hand. Per document:

```json
{"62": {"title": "Commercial Waste and Recycling Service Agreement",
        "clauses": [{"id": 1403, "t": "renewal", "p": 3, "x": "2.1 The initial term ..."}],
        "fields":  [{"f": "notice_period_days", "v": "90", "c": 0.9, "cl": 1403, "p": 3}]}}
```

Plus, typed into the page's script from the same database: the folder list (file, format, short description, id,
parent id), one summary row per document (the main table's columns), the one-document story's values, obligations and
failed checks, the effective-terms comparison for the amended record, and the four queries' results. Check every one
against the database before publishing.

Highlighting values in text: search each clause for the value in the forms a document writes it (a date as
"November 30, 2026" and "30 November 2026"; days as "(30) days"; money with thousands separators). Values that cannot
be quoted literally (true/false, "2 times annual fees") point to their source clause instead, or say "judged from the
whole text". Expect roughly 60% of values to get a highlight; say so if asked.

## 4. Adapting it to another product

The page is not about contracts; it is about input → parts → values with sources → rows → answers. Map the product:

| Page concept | Contracts (original) | Other examples |
|---|---|---|
| Input | A contract PDF | An invoice, a claim form, a support ticket, a call transcript, a medical record, a CV |
| Parts | Clauses with types | Line items, sections, fields, utterances |
| Values with source | Terms with clause and page | Amounts with line, diagnoses with paragraph, skills with sentence |
| Rows | contracts, field_extractions, obligations, check_results | The product's own tables |
| Relationships | Schedule → master agreement; amendment overrides | Credit note → invoice; follow-up → ticket |
| Duplicate | Same file under another name | Same invoice sent twice |
| The "aha" | A renewal deadline already passed | An invoice above the agreed rate; an SLA breach nobody saw |
| Four questions | Act by, uncapped, can't leave, spend by site | The four questions the audience asks most |

Keep the two-story structure and the five stage names if they fit; rename stages only if the product's pipeline is
genuinely different.

## 5. Building and publishing

- One self-contained HTML file: inline CSS and JS, data in a `<script type="application/json">` block (escape `</`
  as `<\/`), Google Fonts the only external request. Keep a local copy wrapped in `<!doctype html>` so it opens from
  disk on a presenting laptop without a network.
- Publish as a private page (in Claude, an Artifact) and give the user the link; commit the source, the local copy,
  the exported data and the export script to the repo.
- Check once in a browser (desktop and 400px wide, light and dark): no console errors, no sideways scroll, runs
  complete, every file opens.

## 6. Pitfalls found in the original

- Clause ids and types written from memory did not match the database. Export, don't recall.
- A number in the copy ("a library of 44 clause types") was out of date (49). Every number in prose comes from data.
- Animation colours: a "row added" highlight animation that fades the background to transparent made white-on-teal
  tags invisible. Fade opacity, not background.
- Dates are frozen at export ("76 days ago"); the product's live screens move on. Warn the presenter.
