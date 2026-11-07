# ContractIQ redesign (design only, not yet implemented in the front end)

* `boards/` — one `.dc.html` file per screen (39 boards: every screen group, dialogs, states, dark theme, phone layouts) and `canvas.json` (the layout).
  The same canvas is published as a private artifact; these files are the source of truth and can be re-imported.
* `generators/` — the small Python helpers that produced the boards (`lib.py` has the shell and components; `a.py` to `h.py` build the screens).
  Paths inside point at a scratch folder; edit `ROOT` in `lib.py` to regenerate.
* Sample numbers and dates on the boards are illustrative and are not consistent across all boards yet.
* Principles: decide don't browse; every number carries its evidence; severity is shape + word + colour; one honest Demo/Live switch.
