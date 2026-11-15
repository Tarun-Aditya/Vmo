# Demo runbook: contracts in, data out (about 14 minutes)

Three acts: **these are the contracts** (paper nobody reads twice), **this is how the machine reads them** (first one document opened up step by step,
then a whole folder at scale), and **this is what you can do once it is data** (deadlines, risk, money, questions in plain English).

The contracts read live are fictional but written like real US hotel supplier paper (`data/realistic_hotel`, see its README): five core contracts, plus a
cleaning contractor's NDA, master agreement, two schedules and a scanned amendment. The Seabright portfolio (32 documents) is already loaded, so after the
live part every screen has a full portfolio to show.

## Before you start (5 minutes, once)

1. Start the hotel edition (`make showcase`, or "Run it from a clean clone" in the README) and open the app.
2. Choose the engine with the header switch:
   * **Demo mode on** (offline rules): identical every run, no internet. About 20 seconds for a long contract on a laptop, a few seconds for a short one;
     most of it is indexing. The folder of 11 takes about two minutes.
   * **Demo mode off** (Claude): Claude reads each document. Noticeably slower and slightly different each run: rehearse once in this mode and time it.
3. Open **Add contracts** and press **Reset demo**, so everything can be added live.
4. Optional: one of your own PDFs on the desktop, to read instead of a sample (reset removes it afterwards).

## Act 1: the contracts (2 minutes)

**Screen:** Add contracts → **One document**, sample *Waste hauling…* → **Open original**.

* "This is a waste hauler's contract for one of our hotels: six pages, the supplier's own form. Somewhere in here is a date that costs money."
* Scroll to section 2.2, the paragraph in capitals: "It renews for another **three years** unless we cancel by certified mail, in a window between 180 and 90 days
  before the end. Nobody calendared it. The window closed on 1 September."
* "Now multiply this by every supplier at every hotel: food, maintenance, software, parking, cleaning. Most of them in a shared drive, read once at signature."

## Act 2a: one document, opened up (3 minutes)

**Screen:** One document → *Waste hauling…* → **Read this document**. The five steps at the top of the page are the talk track; the document's own step
rail turns green under them.

| Step | What to say | What to point at |
|---|---|---|
| **1 Read** | "First the text, with its page numbers. A Word file has no fixed pages, so none are invented; a scan goes through OCR." | "6 pages · 1,915 words" |
| **2 Structure** | "It splits the contract into clauses and recognises each one, wherever the supplier put it and whatever they called it." | "20 clauses · 11 kinds" |
| **3 Extract** | "Then the terms that matter: dates, renewal and notice, value, payment, liability cap, exit rights, law, personal data, who signed. Each from a clause and a page, with a confidence." | The terms table |
| **4 Index** | "Every clause becomes a vector, a fingerprint of its meaning, so later you can ask 'what happens if we end this early' and land on the liquidated-damages clause, though it never says 'end early'." | "20 vectors × 384 dimensions" |
| **5 Check** | "Last, it is compared with your standards: what is missing, what is risky, and the last day to act." | "Last day to stop renewal: 01 Sept 2026" |

When it finishes, the view opens: the document as read (left), the terms (right).

* Click **Notice to stop renewal (days) · 90**: the renewal clause lights up with "90" marked. "Every number can be traced to the words it came from."
* Click **End date**: "30 November 2026" is marked in the term clause. Click **Signed for us by**: the signature block.
* "Nobody typed any of this. If a value is wrong, it is corrected on the contract page, and the correction survives the next read."

## Act 2b: a folder of documents (3 minutes)

**Screen:** switch to **A folder of documents** → **Read the folder (11 files)**.

"One document is a demo. The job is the shared drive." While the rows fill in, the counters at the top keep score: documents, pages, clauses indexed,
terms extracted, links, duplicates, elapsed time. Point at four rows as they finish:

* **The cleaning master agreement and its two schedules**: the schedules are recognised as *under* the master agreement, so they inherit its terms.
* **Amendment No. 1, a scanned signed copy** ("scan, OCR"): read from the image, linked to the master agreement, and it **changes its end date and payment terms**.
  "The current terms are what the amendment says, not what the original says. That is what people get wrong in spreadsheets."
* **The waste contract** shows *already read*: "We read it a minute ago. It is not read twice."
* **The signed copy of the food contract**: *duplicate*. "Same file under another name: caught by its fingerprint, not stored twice."

When it finishes, press **Read the folder again**: every file comes back *already read* in a few seconds. "This is what runs every night against the
shared drive, SharePoint or the contracts mailbox: only what is new or changed is read."

The **Now part of the portfolio** panel then sums it up: contracts added, annual value, clauses indexed, contracts with no liability cap, guest personal data,
and **Act on next**: the cleaning NDA expires in 2 days, the HVAC contract's renewal notice is due in 17 days.

## Act 3: the power of the data (5 minutes)

Use the links in the summary panel, in this order.

1. **Renewals** (*See them on Renewals →*, 1 min). "The new contracts sit on the timeline with the rest of the portfolio. The diamond is the last day to act,
   not the expiry date. Decisions this month: the waste contract (too late; it renews unless we negotiate), the HVAC contract (17 days)."
   Record a decision on the HVAC contract: *Renegotiate*, owner, note.
2. **Ask the whole portfolio** (1.5 min):
   * *Which auto-renewing contracts have already passed their notice deadline?* (the waste contract beside older ones)
   * *Which vendors have uncapped liability?* (valet parking and waste hauling among them)
   * *Who are the top 5 vendors by annual value?* (the new food distributor first)
   Open **How I got this** on one answer: "It wrote this SQL; you can check it."
3. **Ask one contract** (1 min): *Prairie: What happens if we end this contract early?* returns the liquidated-damages clause with its page and match score;
   *Keystone: Who pays if a guest's car is damaged?* returns Article VII. "Search by meaning over the clauses indexed in act 2."
4. **The cleaning master agreement** (1 min): open it from the folder table (*under Master Services Agreement*). **Hierarchy and effective terms**: the two
   schedules beneath it, and payment terms of 30 days and an end date of February 2029, each showing it comes from Amendment No. 1.
5. **My hotel** (30 s, optional): Seabright Airport Inn: the waste contract's missed notice is on the general manager's to-do list with everything else there.

**Close (30 s).** "Signed paper in, decisions out: every date, value and risk term traced to its source, the current terms after every amendment,
searchable by meaning, checked against your standards, and on the screens where people act. Next: your own contracts, through the same door."

## Reset and rehearse

* **Reset demo** removes everything added on Add contracts (samples, the folder, your own files) and all data derived from them; nothing else is touched.
* `python ../scripts/load_realistic_hotel.py` (from `backend/`) adds the five core contracts without the screen, to rehearse act 3 alone.
* If one document fails on stage, its row says why and the rest continue.

## What is real and what is not

* Real: the pipeline (the same code behind the folder watcher, the connectors and email intake), the extraction, OCR, the vectors and search, parent linking,
  amendment overrides, duplicate and change detection, the checks, and every number on every screen.
* Fictional: the companies, people and contracts. They were written by Claude Code to read like real ones, and the offline rules were improved on them,
  so their 100% extraction score shows the engine reads such paper, not an independent accuracy figure (see `data/realistic_hotel/README.md`).
* The Seabright portfolio is generated; invoices, SLA reports and the ERP, e-signature and drive connectors are labelled simulators.
