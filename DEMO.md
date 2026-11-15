# Demo runbook: contracts in, data out (about 12 minutes)

The story has three acts: **these are the contracts** (paper nobody reads twice), **this is what the machine does with them** (extraction and indexing,
step by step, live), and **this is what you can do once it is data** (deadlines, risk, money, questions in plain English).

The five contracts used live are fictional but written like real US hotel supplier paper: `data/realistic_hotel` (see its README).
The other 32 documents (the Seabright portfolio) are already loaded, so after the live part every screen has a full portfolio to show.

## Before you start (5 minutes, once)

1. Start the hotel edition (`make showcase`, or the commands under "Run it from a clean clone" in the README) and open the app.
2. Choose the engine in the header switch:
   * **Demo mode on** (offline rules): fast, identical every time, no internet. About 20 seconds per document on a laptop; most of it is indexing.
   * **Demo mode off** (Claude): Claude reads each document. Slower (noticeably slower per document: time it in rehearsal) and slightly different every run. Use it when the audience
     will want to know "is this AI?". Rehearse once in that mode first.
3. Go to **Add contracts**. If the five samples show "✓ in portfolio", press **Reset demo** so they can be added live.
4. Have the five originals at hand: each row has **Open original** (the PDFs open in the browser; the Word files download).
5. Optional: keep one of your own PDFs on the desktop to drag in (it is read the same way; reset removes it afterwards).

## Act 1: the contracts (2 minutes)

**Screen:** Add contracts → **Open original** on the waste contract (PDF), then the HVAC contract (Word).

* "These are five signed supplier contracts from one hotel group: food, HVAC maintenance, the revenue-management system, valet parking, waste hauling.
  Six to nine pages each, each in the supplier's own format. Between them: three different renewal mechanisms, two contracts with no cap on liability,
  a data processing addendum buried in an exhibit, and one deadline that has already been missed."
* Scroll the waste contract to section 2.2, the capitals paragraph: "Renews for another **three years** unless you cancel by certified mail, in a window between
  180 and 90 days before the end. Nobody calendared it. The window closed on 1 September."
* "Today this lives in a shared drive. Finding that sentence means somebody reading it. Let's turn the paper into data."

## Act 2: extraction and indexing (4 minutes)

**Screen:** Add contracts. All five samples are ticked; press **Read 5 documents**.

Talk over the five step cards at the top while the first document runs, then point at its card as each step turns green:

| Step | What to say | What to point at |
|---|---|---|
| **1 Read** | "First the text and the page numbers, from PDF or Word. A scan goes through OCR." | "8 pages · 3,283 words" |
| **2 Structure** | "It splits the contract into clauses and recognises each one: renewal, liability, payment, insurance, data protection. Wherever the supplier put it and whatever they called it." | The clause chips |
| **3 Extract** | "Then the terms that matter: dates, renewal and notice period, value, payment terms, liability cap, exit rights, governing law, personal data, who signed. Each with the page it came from and a confidence." | The terms table: page and confidence columns |
| **4 Index** | "Every clause becomes a vector: a fingerprint of its meaning. That is what lets you later ask 'what happens if we end this early' and find the liquidated-damages clause, though it never uses the words 'end early'." | "27 vectors × 384" |
| **5 Check** | "Finally it is compared with your own standards: missing clauses, risky terms, and the last day to act." | "Last day to stop renewal", the severity chips |

Points worth making while the other four run:

* The **Engine** label says which engine read them (offline rules or Claude). The same pipeline reads the watched folder, the Google Drive / SharePoint
  connectors and email intake; this screen only makes it visible.
* Every value links back to its source. Click **Open with sources →** on a finished card: the contract page highlights the passage each value came from,
  and a wrong value can be corrected there (the correction is kept when the document is read again).
* The Word files show no page numbers, on purpose: Word has no fixed pages, so none are invented.

When the **Now part of the portfolio** panel appears: "Five contracts, $4.5M a year, 112 clauses indexed, two with no liability cap, one handling guest
personal data, and these are the deadlines." Point at **Act on next**: the waste contract's notice passed 75 days ago, the HVAC contract's is in 17 days.

## Act 3: the power of the data (5 minutes)

Go through the links in the summary panel, in this order.

1. **Renewals** (*See them on Renewals →*, 1 min). "The new contracts are already on the timeline with the rest of the portfolio. The diamond is the
   last day to act, not the expiry date. Decisions this month: the waste contract (too late, it renews unless we negotiate), the HVAC contract (17 days left)."
   Record a decision on the HVAC contract: *Renegotiate*, owner, note.
2. **Ask the whole portfolio** (1.5 min). Click, in turn:
   * *Which auto-renewing contracts have already passed their notice deadline?* (the waste contract appears beside older ones)
   * *Which vendors have uncapped liability?* (valet and waste among them)
   * *Who are the top 5 vendors by annual value?* (the new food distributor is first)
   Open **How I got this** on one answer: "It wrote this SQL; you can check it."
3. **Ask one contract** (1 min). *Prairie: What happens if we end this contract early?* The answer is the liquidated-damages clause, with page and match.
   Then *Keystone: Who pays if a guest's car is damaged?*: Article VII, vehicle damage. "Semantic search over the clauses we indexed in act 2."
4. **One contract, end to end** (1 min). Open the valet contract: terms beside the document with source highlights, the checklist (no liability cap,
   no data protection clause), obligations created from its clauses (yearly insurance evidence, a 24-hour notice of any data incident). "Everything you saw on the intake card, kept."
5. **My hotel** (30 s, optional). Pick Seabright Airport Inn: the waste contract's missed notice sits on the general manager's to-do list with everything
   else at that hotel.

**Close (30 s).** "Signed paper in, decisions out: every date, value and risk term with its source, searchable by meaning, checked against your standards,
and on the screens where people act. Next: your own contracts, through the same door."

## Reset and rehearse

* **Reset demo** on Add contracts removes the five (and any file you dragged in) with everything derived from them; nothing else is touched.
* From the command line, `python ../scripts/load_realistic_hotel.py` (in `backend/`) adds them without the screen, for example to rehearse act 3 alone.
* If a step fails on stage, the card says why and the others continue; **Reset demo** and run it again.

## What is real and what is not

* Real: the pipeline (the same code for every intake route), the extraction, the vectors and search, the checks, every number on every screen.
* Fictional: the companies, people and contracts. The five contracts were written by Claude Code to read like real ones, and the offline rules were improved
  on them, so their 100% extraction score shows the engine reads such paper, not an independent accuracy figure (see `data/realistic_hotel/README.md`).
* The Seabright portfolio is generated; invoices, SLA reports and the ERP, e-signature and drive connectors are labelled simulators.
