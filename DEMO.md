# Demo runbook: contracts in, data out (about 14 minutes)

Three acts: **these are the contracts** (paper nobody reads twice), **how the machine reads them** (the continuous pipeline: one document, then any number),
and **what you can do once it is data** (the repository, deadlines, questions in plain English over all documents or the ones you tick).

Everything in act 2 happens where it happens in production: **Admin → Pipeline**. Contracts arrive from the watched folders, the connectors (drives,
SharePoint, ERP, mailbox) or an upload; every run, whatever started it and however many documents it holds, shows document by document in the live run panel.

The documents read live are fictional but written like real US hotel supplier paper (`data/realistic_hotel`, see its README): a cleaning contractor's
NDA, master agreement, two schedules and a scanned amendment; food, HVAC, revenue-management software, valet and waste contracts; and one exact copy.
The Seabright portfolio (32 documents) is already loaded, so every screen has a full portfolio to show.

**Presenting to leadership?** Lead with the idea, not the product: the decks and the click-through *From paper to rows* page in
`reports/presentation/` (see its README) come first, and this runbook's act 3 follows as the proof. The page covers acts 1 and 2 without the app.

## Before you start (5 minutes, once)

1. Start the hotel edition (`make showcase`, or "Run it from a clean clone" in the README) with the simulators on, and open the app.
2. Choose the engine with the header switch:
   * **Demo mode on** (offline rules): identical every run, no internet. The sample folder of 11 takes about two minutes; a long contract about 20 seconds,
     mostly indexing.
   * **Demo mode off** (Claude): Claude reads each document. Slower and slightly different each run: rehearse once in this mode and time it.
3. **Record Claude's results once** (recommended): with Demo mode **off** and Claude configured, run `python ../scripts/record_demo.py` from `backend/`.
   It reads the sample documents and asks the demo questions (`data/realistic_hotel/demo_questions.json`) with Claude, and saves the results in
   `data/realistic_hotel/recorded.json`; commit that file. In Demo mode the sample documents then show Claude's terms and the recorded questions Claude's
   answers, instantly and identically every run, without internet. They are labelled *recorded (Claude, date)* in the live run and *recorded answer* in Ask.
   Anything else (your own files, other questions) is read live by the offline engine. The file in the repository was recorded with the offline engine,
   because the session that built this had no Claude access.
4. **Admin → Pipeline → Demo sample folder**: if it says the files are in the portfolio, press **Remove it**.
5. Have the originals at hand (`data/realistic_hotel/docs`), and optionally a PDF of your own to drag in.

## Act 1: the contracts (2 minutes)

Open `prairie_waste_services.pdf`.

* "A waste hauler's contract for one of our hotels: six pages, the supplier's own form. Somewhere in here is a date that costs money."
* Section 2.2, the paragraph in capitals: "It renews for another **three years** unless we cancel by certified mail, in a window between 180 and 90 days before
  the end. Nobody calendared it. The window closed on 1 September."
* "Multiply this by every supplier at every hotel. Most of it sits in a shared drive, read once at signature."

## Act 2: the pipeline (5 minutes)

**Screen:** Admin → Pipeline.

1. **Where contracts come from (30 s).** The pipeline cards: executed contracts read on a schedule (every 2 hours) from the watched folders; drafts read
   as soon as a file appears; the Sources list (drives, SharePoint, ERP, mailbox). "Nobody uploads anything by hand in production: this runs by itself."
2. **A folder of documents (2 min).** **Demo sample folder → Put the folder in the inbox and read it.** The **Live run** panel fills in, one row per document,
   with the counters on top (documents, pages read, clauses indexed, terms extracted, links, duplicates, elapsed). The five steps are in its first line:
   *read* (text and pages; scans by OCR), *recognise* the clauses, *extract* the terms with their clause and page, *index* the clauses as vectors for search
   by meaning, *check* against your standards. As rows finish, point at:
   * the two **schedules** and the **amendment**: *under Master Services Agreement*;
   * the **amendment**, *scan, read by OCR*, which **changes its end date and payment terms**;
   * the **signed copy**: *duplicate*, "the same file under another name, not stored twice".
3. **One document, opened up (1.5 min).** Click the waste contract's row: its terms (dates, notice, payment, cap, exit, law, personal data, signers) with page
   and confidence, the checks that failed, the last day to act. **Open the contract with its sources →**: the contract page shows the document beside the
   terms; click a term and the passage it came from is highlighted. "Nobody typed any of this; a wrong value is corrected here and survives the next read."
4. **Again (30 s).** Press **Put the folder in the inbox again**: every row comes back *already read* in seconds. "This is the nightly run against the shared
   drive: only what is new or changed is read." Optionally drag your own PDF into **Add documents**: it appears in the live run the same way.

## Act 3: the power of the data (5 minutes)

1. **Contracts (1.5 min).** The repository: every agreement with its schedules, amendments and NDAs beneath it, and the terms a VMO scans for: start, end,
   **last day to act** (the notice date when it renews by itself, ↻), value, payment, liability, exit, signatures, flags. The cleaning master agreement shows
   30-day payment and a 2029 end date: "the amendment's terms, not the original's". Saved views: **Expiring**, **Flagged**, **Unsigned**.
2. **Renewals (1 min).** The last day to act on a timeline. Decisions this month: the waste contract (too late; it renews unless we negotiate), the HVAC
   contract (17 days). Record a decision.
3. **Ask, all documents (1 min).** Every document is ticked: *Which auto-renewing contracts have already passed their notice deadline?* and *Which vendors have
   uncapped liability?* Open **How I got this**: "It wrote this SQL; you can check it."
4. **Ask, the documents you tick (1.5 min).** Untick **All documents**, search "Meridian", **Tick shown** (the cleaning contractor's five documents):
   * *Show start date, end date and payment terms*: a table from those documents only, with the amended terms;
   * *What are the insurance requirements?*: each document's insurance clause;
   * *What are the termination terms?*: the closest clauses by meaning, with page and match.
   Tick one contract only (the waste contract): *What happens if we end this contract early?* returns the liquidated-damages clause.

**Close (30 s).** "Signed paper in, decisions out: every date, value and risk term traced to its source, the current terms after every amendment,
searchable by meaning, checked against your standards, continuously, for every document that arrives."

## Reset and rehearse

* **Admin → Pipeline → Demo sample folder → Remove it** removes the folder and everything read from it; nothing else is touched.
* `python ../scripts/load_realistic_hotel.py` (from `backend/`) puts the five core contracts in the same folder without the screen, to rehearse act 3 alone.
* A document that fails shows *failed* in its row with the reason; the rest of the run continues.

## What is real and what is not

* Real: the pipeline (one code path for schedule, folder watch, connectors, mailbox and upload), extraction, OCR, the vectors and search, parent linking,
  amendment overrides, duplicate and change detection, the checks, and every number on every screen.
* Fictional: the companies, people and contracts. They were written by Claude Code to read like real ones, and the offline rules were improved on them,
  so their 100% extraction score shows the engine reads such paper, not an independent accuracy figure (see `data/realistic_hotel/README.md`).
* The Seabright portfolio is generated; invoices, SLA reports and the ERP, e-signature and drive connectors are labelled simulators.
