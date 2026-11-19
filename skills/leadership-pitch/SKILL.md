---
name: leadership-pitch
description: Turn a product repository into an idea-first leadership pitch - three slide decks (the idea, the idea for one business domain or persona, solution and architecture), a click-through "paper to rows" page that shows unstructured inputs becoming structured data before the product demo, and the kit around them (sample documents with a presenter guide, a narrated demo video, an invitation email). Use this whenever someone wants to pitch, present or "sell" what a repo or product does to leadership, executives, a steering group, investors or a non-technical audience; asks for a deck, PPT, slides or a presentation about their project; wants to explain an AI or data idea before demoing the product; or wants a demo, walkthrough video, talk track or invite for such a pitch, even if they don't name all the pieces.
---

# Leadership pitch: idea first, product as proof

This skill packages a method that worked for pitching an AI product to leadership: explain the idea in plain business
terms first, show the transformation that makes it possible, and only then show the product as proof. It was built
on a contract-intelligence product (AI reads contracts and turns them into relational data), but the method applies
to any product whose value comes from turning messy input into structured data or automated work.

## The core belief behind it

Leaders do not buy features; they buy a change in how the business works. A product demo shown first invites
feature-by-feature judgment ("does it do X?"). Shown last, after the audience understands the idea and has seen the
raw material being transformed, the same demo reads as evidence. So the order is fixed:

1. **The problem**, in the audience's words: the manual work, the risk, the cost, one document at a time.
2. **The idea**: what changes once the work is data (or automated), and why it is possible now.
3. **The transformation**: one real input, then many, becoming structured data (the paper-to-rows page).
4. **The product**: the same data running real business processes.
5. **The ask**: a measured pilot with a decision at the end.

## Workflow

### 1. Understand the repo and the audience (do this before any slide)

- Read the README, handover or status notes, the data model, and any measured results. Note what is *built and
  tested*, what is *measured* (with numbers and their sources), and what is *not yet done*. The pitch may only claim
  the first two.
- Find the one sentence the whole pitch hangs on. For the original: "AI turns contract documents into structured,
  related data, and every contract process then runs on that data." Write yours down; every slide must serve it.
- Identify the audience and their vocabulary (a hotel owner says "property", not "tenant"; a CFO says "cash", not
  "throughput"). Ask the user if unclear: who is in the room, what decision they can make, how long you have.

Read `references/thinking.md` for the thought process, the simplification rules and the mistakes the user corrected
along the way. These corrections are the most valuable part of this skill.

### 2. Build the three decks

| Deck | Purpose | Audience |
|---|---|---|
| **1. The idea** | Why, what changes, why now, proof so far, the ask | Everyone |
| **2. The idea for one domain or persona** | The *same thesis* told from inside one business (e.g. a hotel group: the property manager and the owner) | The business owners |
| **3. Solution and architecture** | How it actually works, layer by layer, with honest limits | Technical leaders, follow-up questions |

Deck 2 is not a different message. It repeats deck 1's problem and idea in the domain's language and roles. When the
user first got a domain deck about "visibility and hierarchy", they rejected it: the point is still easing the
manual operations. Keep the thesis identical across decks; change only the examples and the people.

Slide-by-slide blueprints are in `references/deck-outlines.md`. Design theme and slide-building rules are in
`references/design-theme.md`. A complete example deck (the idea deck, 11 slides) is in `assets/example-deck-idea/`.

Also offer a combined deck (all three in order, each starting with its own cover) so one link covers the session.

### 3. Build the "paper to rows" page (the missing piece)

Between the idea decks and the product there is a gap: the audience has been told documents become data, but has
not seen it happen. Build a standalone, click-through page that shows it, using the product's real output:

- **One document**: the file, split into typed parts, each value highlighted in its sentence, then the rows it
  becomes, then what those rows reveal (the "aha", e.g. a renewal deadline that already passed).
- **Many documents** (about ten, mixed formats, with a scan, related files and a duplicate): the same pipeline
  file after file, links between files, an amendment changing terms, a duplicate turned away, then four business
  questions each answered by one query.
- Live animated runs on "Run", and a document view that opens when any file is clicked.

Read `references/paper-to-rows.md` for the structure, the data to export and how to adapt the example in
`assets/paper-to-rows-example.html`. Use real exported data only; never type values in.

### 4. Build the demo kit

Read `references/demo-kit.md` for:
- the **sample documents** packaged in order, with a **presenter guide** that names, per document, the page or
  section of each key term and the manual work it implies (the presenter opens them before the page);
- a **narrated demo video** recorded with Playwright and an offline voice (`scripts/presentation_storyboard.js`,
  `scripts/make_narration.py`);
- the **invitation email** (`assets/email-template.md`);
- the **session order** and a README for the presentation folder.

### 5. Check before handing over

- Every number on a slide, the page or in the email traces to the repo's data or measured results, or is a clearly
  marked `[placeholder]` for the user to fill. Fictional sample data is labelled as such.
- Run the overflow check on every deck (`scripts/check-overflow.js`); nothing below the bottom margin.
- Click through the page in a browser at desktop and phone width; no console errors, no sideways scroll.
- Watch the video once at the end; captions, voice and screen must say the same thing. (The original recording
  caught a stale cached answer contradicting the narration; fix the product, not the narration.)
- Commit the presentation folder (decks' source files, the page, the documents, the email, the video and its
  scripts, and a README) to the repo so it survives, and give the user every published link.

## What to tell the user at the end

The links (decks, combined deck, page), where the source files live in the repo, the session order with timings,
anything that needs filling in (placeholders, real figures, dates that will go stale), and that published links are
private until shared.
