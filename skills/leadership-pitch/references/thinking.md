# Thinking: how the pitch was reasoned out, and what the user corrected

Read this before drafting anything. The method came from several rounds of feedback; each correction below is a
mistake that is easy to make again.

## Contents
1. The narrative arc
2. Simplifying for a leadership audience
3. Corrections from the user (the lessons)
4. Honesty rules
5. Questions to ask the user

## 1. The narrative arc

The original thesis, stated by the user: *"the power of bringing unstructured data into a structured form, and
helping the business processes and outcomes driven by AI. The contract processes (renewal, obligations, drafting,
checking, tracking, alerting) are manual work done one document at a time. Once the data is in a structured format we
can do anything with it. Before, all of this lived in documents and PDFs, which is fine for a couple of them, but
large-enterprise automation needs structure, and AI can now create it."*

Turn any product into the same arc:

| Step | Question it answers | Original example |
|---|---|---|
| Problem | What is manual today, and what does it cost? | Every contract read by hand; renewals missed; terms copied into spreadsheets |
| Idea | What changes once it is data? | Contracts become related rows; every process runs on them |
| Why now | Why couldn't we do this before? | Automation always needed structured input; AI can now create it from documents |
| How | What happens to one input? | A continuous pipeline: read, structure, extract, index, check |
| What it enables | Which outcomes, for whom? | Renewals, obligations, redlines, spend, risk, questions in plain English |
| Proof | Does it work? | Measured on test data; our own data is the next test |
| Ask | What decision do we want? | A pilot on our own contracts, measured, with a decision at the end |

The asset is the data, not the screens. Say so on the demo slide: "The product is the proof. The asset is the data."

## 2. Simplifying for a leadership audience

- **One idea per slide**, written as a full-sentence headline that states the point ("Every contract process changes
  once the terms are data"), not a topic label ("Benefits").
- **Business words, not system words**: "the last day to act" (not "notice_deadline"), "who owes what by when" (not
  "obligation extraction"), "the clause it came from" (not "provenance").
- **Before/after beats feature lists**: the strongest slide in the original was a two-column "without structured
  data / with structured data" comparison, one row per process.
- **Concrete over abstract**: one real example (a waste contract that silently renewed for three years) does more
  than any statistic.
- **Show the work once**: the paper-to-rows page shows the mechanism; the decks only need to promise it.
- **Keep architecture out of the idea decks**: a dedicated third deck, used only if the room wants it.
- **Speaker notes carry the detail**: each slide's notes hold the full talk track, so the slide itself stays sparse.

## 3. Corrections from the user (the lessons)

1. **Idea first, product second.** The user said: "I'm not going to showcase the product first. I'll make them
   understand what I'm trying to build, the idea, and then the outcome of the data is shown in the product. What we
   can do with the data is secondary." Never open with screens.
2. **A domain deck keeps the same thesis.** A deck "from the property manager and owner perspective" was first built
   around visibility and hierarchy (cluster, city, group roll-ups). Rejected: "the point is the operation of
   contracts and how we are easing it; the first deck says exactly that; I need the same problem, from the hotel
   owner's perspective." Change the examples and roles, not the message.
3. **Show the transformation separately, not inside the product.** The user asked for "something else, just for
   the presentation: the missing piece showing one versus ten documents, and then the product shows how the data is
   used." The product is not the right place to explain ingestion; a purpose-built page is.
4. **One document versus a folder.** Explaining one document deeply, then showing it scales to a folder, is the
   structure the user asked for. "Deep one, then scale."
5. **Ingestion belongs in the admin pipeline, not a feature page** (when you touch the product itself): intake is
   continuous system behaviour, not a user feature.
6. **Leave the name aside.** Product names were explored and dropped. Don't spend the pitch on branding; use plain
   descriptions until the user picks a name.
7. **Show the documents by hand first.** Before the page, the presenter opens each sample document and explains the
   manual work. The pain must be felt before the solution is shown.
8. **Voice matters in a video.** A captions-only recording was not enough; the user wanted a voice-over.
9. **Agentic framing must be defensible.** When the user wanted "agentic AI and agents" in the email, it was used,
   with a prepared answer: the reading pipeline is a fixed sequence; what makes it agentic is that it works on its
   own (watches, reads, links, checks, raises actions) and that the question assistant chooses its own tools.

## 4. Honesty rules

- Claim only what is built and measured. "Accuracy on our own data has not been measured yet" belongs on the proof
  slide; leadership trusts a pitch that names its limits.
- Never invent a statistic, quote or customer. Use `[bracketed placeholders]` for figures the user must supply
  (hours per document, number of contracts, cost of a missed renewal) and list them in your reply.
- Label fictional sample data as fictional and samples as samples, in the decks, the page and the email.
- Every value on the paper-to-rows page comes from the product's real output, exported by a script; verify the
  page against the database before publishing, and re-check after any fix.
- If the demo shows something wrong (a stale cache, a wrong count), fix the product and re-record. Do not reword the
  narration around a bug.
- Dates go stale: note which lines depend on today's date ("76 days ago", "two weeks away").

## 5. Questions to ask the user (only if the repo does not answer them)

- Who is in the room, and what can they decide?
- How long is the slot, and is there a demo machine?
- Which domain or persona should deck 2 speak to?
- Which measured results may be quoted, and is any real customer data allowed on screen? (Default: fictional only.)
- Is there a design system or house style? (Default: the theme in `design-theme.md`.)
