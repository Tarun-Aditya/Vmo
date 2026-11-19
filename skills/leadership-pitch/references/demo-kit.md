# The demo kit: documents, presenter guide, video with voice-over, email, session order

## Session order (about 40 minutes)

1. **Deck 1, the idea** (10 min)
2. **Deck 2, the domain or persona** (8 min)
3. **The documents, the manual way** (4 min): open the sample files one by one with the presenter guide
4. **Paper to rows** (8 min): one document, then the folder
5. **The product** (5 min): two or three screens and two plain-English questions on the same data
6. **Deck 3, architecture** (as needed): for the technical audience or questions

Put this order, the links and the timings in a `README.md` in the presentation folder.

## Sample documents and presenter guide

Package the exact files the paper-to-rows page reads, numbered in the page's order (`01_...` to `11_...`), including
the renamed duplicate, plus a presenter guide (Markdown, and Word via `pandoc` so it opens anywhere), and zip them.

The guide gives, per document: what it is and its format; **where each key term sits** (PDF page numbers, or section
numbers for Word files, which have no fixed pages); the values to point at; and one line on the manual work it
implies ("the amendment is a picture: someone has to notice the spreadsheet row is now wrong"). Group related files,
spend most time on the "aha" document, end on the duplicate, and finish with the line that switches to the page.
Template: `assets/presenter-guide-template.md`.

Verify every page number against the files (for PDFs, `pdftotext -f N -l N` per page and search) and every value
against the source text. The original guide had two wrong page numbers before this check.

## Narrated demo video

Two scripts in `scripts/`, adapted per product:

- `presentation_storyboard.js` (Playwright): opens the local paper-to-rows page, walks both stories (waiting for the
  runs to finish, clicking value chips, opening documents), then switches to the running product for two or three
  screens and two questions. Each step shows a caption, holds at least as long as its narration line, takes a
  screenshot and records its start time; at the end, ffmpeg mixes the narration clips in at those times and writes
  an mp4, plus a `report.md` of passed and failed steps. Without narration files it records silently with captions.
- `make_narration.py` speaks one line per step from a JSON file (`assets/narration-example.json`) with **Piper**,
  an offline text-to-speech engine, writing `narration/NN.wav` and `durations.json`. Install Piper outside the
  project (`python -m venv tts && tts/bin/pip install piper-tts`) and download a voice from
  `huggingface.co/rhasspy/piper-voices` (the original used `en_US/lessac/high`). Don't commit the audio; it can be
  regenerated.

Write narration the way the presenter would say it: short sentences, one idea each, describing what is on screen.
Then watch the result once. In the original, the last Ask answer on screen contradicted the narration because the
product served a stale cached answer: fix the product and re-record. Offer the user the alternative of recording
their own voice over the silent cut, using the narration as their script.

## Invitation email

Template: `assets/email-template.md`. Structure, in the order that worked:
1. Subject: what it is and who it is for ("Contract Intelligence for Property Managers").
2. The concept in one line (a pipeline that turns unstructured information into structured data), and where it is
   being applied.
3. The problem, in the audience's words, ending with "found by hand, one document at a time, and often too late".
4. The idea, with the framing the user wants (e.g. "agentic AI: agents pick up each document as it lands ...").
5. Manual way vs the new way: paired lines (email clients break tables).
6. Why it pays back: time, avoided losses, money left on the table, risk, each with a `[placeholder]` for the
   user's real figure.
7. What they will see, in three bullets, and how long it takes.
8. When, where, and "I'd value your view on whether this is worth taking further."

Keep claims defensible: "it works the same way at ten documents or ten thousand" rather than a speed you have not
measured. List every placeholder in your reply.
