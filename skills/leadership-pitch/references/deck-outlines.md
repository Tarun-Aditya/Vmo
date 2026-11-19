# Deck blueprints

Three decks, one thesis. Headlines below are the originals (contract intelligence); replace the subject, keep the
job each slide does. Each slide has an eyebrow label (small, uppercase, accent colour), a full-sentence headline, one
visual idea, and speaker notes holding the full talk track.

## Deck 1: The idea (11 slides, about 10 minutes)

Sections: *Why* (cover to problem) · *The idea* (idea to how) · *What the data enables* (enables, lifecycle) ·
*Proof and the ask* (proof to ask).

| # | Eyebrow | Headline (original) | What the slide does |
|---|---|---|---|
| 1 | AN IDEA FOR LEADERSHIP | From documents to decisions | Cover: the thesis in four words, a one-line subtitle, presenter and date |
| 2 | THE PROBLEM | Our business runs on contracts, but their terms live in documents | The manual reality: 3 to 4 pain cards (missed renewals, terms nobody can find, checks done by hand, work repeated per site) |
| 3 | THE IDEA | AI turns documents into structured, related data | The one-sentence idea as a statement slide, with a simple from → to visual |
| 4 | WITHOUT AND WITH STRUCTURED DATA | Every contract process changes once the terms are data | Two-column table, one row per process: today (manual) vs with data |
| 5 | WHY AI, WHY NOW | Automation always needed structured input. AI can now create it. | Why this was impossible before and possible now |
| 6 | HOW IT WORKS | A continuous pipeline: every document that arrives becomes data | Five steps left to right (read, structure, extract, index, check), each with one line |
| 7 | WHAT THE DATA ENABLES | One source of truth, many outcomes | Hub-and-spoke or card grid of outcomes, all from the same data |
| 8 | ACROSS THE CONTRACT LIFECYCLE | The same data serves every stage, from first draft to renewal | Lifecycle stages with what the data does at each |
| 9 | WHAT THE PROOF OF CONCEPT SHOWS | It works on test contracts. Our own are the next test. | Measured results with sources; what is not measured yet |
| 10 | WHAT YOU WILL SEE NEXT | The product is the proof. The asset is the data. | Handover to the paper-to-rows page and the demo |
| 11 | NEXT STEPS AND THE ASK | A pilot on our own contracts, measured, with a decision at the end | The ask: scope, duration, what is measured, the decision point (dark closing slide) |

## Deck 2: The idea for one domain or persona (12 slides, about 8 minutes)

Same skeleton as deck 1, in the domain's words, plus one slide for the people it helps. The original domain was a
hotel group: the property manager running one hotel, and the owner running many.

| # | Eyebrow | Headline (original) | Note |
|---|---|---|---|
| 1 | AN IDEA FOR HOTEL OPERATIONS | From hotel contracts to hotel operations | Cover |
| 2 | THE PROBLEM | Every hotel runs on supplier contracts, and running them is manual | The domain's suppliers named (cleaning, food, waste, maintenance, parking, software) |
| 3 | THE IDEA | AI turns hotel contracts into structured, related data | Same idea |
| 4 | WITHOUT AND WITH STRUCTURED DATA | Every contract operation changes once the terms are data | Domain operations as rows |
| 5 | WHO IT HELPS | Less manual work at the hotel, and for the owner | The personas and their week, before and after; keep it about easing work |
| 6 | WHY AI, WHY NOW | Automation always needed structured input. AI can now create it. | Same |
| 7 | HOW IT WORKS | A continuous pipeline: every contract that arrives becomes data | Same |
| 8 | WHAT THE DATA ENABLES | One source of truth, the hotel's operations on top | Domain outcomes |
| 9 | ACROSS THE CONTRACT LIFECYCLE | The same data serves every stage of a supplier contract | Same |
| 10 | WHAT THE PROOF OF CONCEPT SHOWS | It works on a test hotel group. Our own hotels are next. | Same honesty |
| 11 | WHAT YOU WILL SEE NEXT | The product is the proof. The asset is the data. | Same |
| 12 | NEXT STEPS AND THE ASK | A pilot on a few of our hotels, measured, with a decision at the end | Domain-scoped ask |

Do not turn deck 2 into a deck about dashboards, roll-ups or hierarchy (cluster, city, region). That was tried and
rejected: it changes the thesis from "easing manual operations" to "visibility".

## Deck 3: Solution and architecture (13 slides, as needed)

Sections: *The whole solution* · *How a document becomes data* (one slide per layer) · *The database and what is
derived* · *Questions, trust, stack, next*.

| # | Eyebrow | Headline (original) | What the slide does |
|---|---|---|---|
| 1 | SOLUTION AND ARCHITECTURE | How documents become data | Cover |
| 2 | THE SOLUTION IN ONE PICTURE | Five layers, from documents to decisions | Layer diagram: sources, pipeline, database, rules, screens and questions |
| 3 | 1 · SOURCES AND INTAKE | Contracts arrive from where they already live | Folders, drives, mailbox, ERP; continuous; duplicates detected |
| 4 | 2 · READ | Any file becomes one text form, pages kept | PDF, Word, scans (OCR); page markers for citations |
| 5 | 3 · STRUCTURE | Clauses found, recognised, and documents linked | Clause types; parent and amendment links |
| 6 | 4 · EXTRACT | Every term with its value, source and confidence | AI or rules; corrections kept |
| 7 | 5 · INDEX | Every clause searchable by meaning, not just words | Vectors, in the same database |
| 8 | THE DATA MODEL | One database, the contract at the centre, sources kept | Core table in the middle, related tables around it, the key views |
| 9 | CHECK AND DERIVE | From stored terms to actions, by rules people can change | Checklist, redline, obligations, renewals, alerts, spend and risk; "configuration, not code" |
| 10 | ASK | Plain-English questions, answered from the data, showing the work | Query planning, read-only access, citations |
| 11 | TRUST AND CONTROL | Built so people can rely on it, and check it | Access, people decide, audit, demo/live, data stays put, measured; what leaves our servers |
| 12 | THE STACK | Mainstream, open components; three containers to run | One row per layer: database, backend, AI, search, reading, frontend, run |
| 13 | BUILT, AND WHAT COMES NEXT | The architecture is in place; the next work is real data and scale | Two cards: built and tested / next (dark closing slide) |

Number the layer slides (1 to 5) because they are a real sequence; nothing else needs numbers.

## Combined deck

Copy all three decks into one, prefixing slide ids per part (`a-`, `b-`, `c-`) so they don't collide, keep each
part's cover, and carry over each part's sections with the part name in the description. Keep the originals too.
