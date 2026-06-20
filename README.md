# freshdesk-stickies

[![CI](https://github.com/mpasternak/freshdesk-stickies/actions/workflows/ci.yml/badge.svg)](https://github.com/mpasternak/freshdesk-stickies/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Desktop **sticky notes** that show your most urgent Freshdesk tickets — **one note
per project or person** — and refresh themselves. Built for [Übersicht](https://tracesof.net/uebersicht/)
on macOS, powered by a tiny dependency-free Python script that talks straight to
the Freshdesk REST API.

The point: instead of staring at a flat ticket list where everything is
"priority: Low", each note shows a **priority-scored** queue (overdue SLA →
deadline soon → priority field → age) so the thing that actually needs you floats
to the top.

<!-- Add a real screenshot of your notes here once installed: -->
![freshdesk-stickies on the desktop](docs/screenshot.png)

```
┌─ Webapp ───────────┐  ┌─ BILLING-ACME ─────┐
│ ⏰ #354 timeouts…  │  │ ⏰🔴 #372 invoice   │
│ 🔴 #372 login bug  │  │ ⏰  #354 export     │
│ 🟡 #385 export CSV │  │ ⏰  #353 domains    │
│ …                  │  │ 🔔 #365 pending     │
└────────────────────┘  └────────────────────┘
```

## How it works

- `freshdesk_lib.py` — fetches open + pending tickets (paginated REST search),
  resolves requesters (disk-cached), computes the priority score, filters by a
  free-text token match over *subject + ticket URL + requester*.
- `fd_list.py "<project>"` — CLI used both for testing (pretty text) and by the
  widget (`--json`).
- `make_widget.py "<project>"` — stamps out a self-contained Übersicht widget
  (`widgets/freshdesk-<slug>.jsx`) for that project, at a chosen screen position.

No third-party Python packages — only the standard library, so the system
`python3` on macOS is enough.

## The priority score

Each open ticket gets a score (higher = more urgent), tunable in one place at the
top of `freshdesk_lib.py`:

| Signal | Weight |
|---|---|
| First-response SLA overdue | +100 |
| Resolution SLA overdue | +80 |
| Any deadline within 24h / 48h | +40 / +20 |
| Priority Urgent / High / Medium | +30 / +20 / +10 |
| Age (per day, capped) | +1/day, max +30 |

Pending tickets are bucketed by age since last activity: 🔔 reminder due
(> 5 days) and 🗑 close candidate (> 10 days). Thresholds are constants.

## The filter

The argument is one free-text filter, split into tokens on non-alphanumerics;
**every** token must appear in the ticket's subject, custom URL, or requester
name/email (case-insensitive).

- `Webapp` → matches `[Webapp] …`, a `webapp.*` URL, etc.
- `BILLING-ACME` → requires both `BILLING` (subject) **and** `ACME` (e.g.
  requester `…@acme.com`) — i.e. the billing topic for the ACME client.
- a surname → matched against the requester.
- no argument → everything.

## Setup

1. **Install Übersicht** (once):
   ```sh
   brew install --cask ubersicht
   ```
   Then launch it.

2. **Configure credentials** (kept in `~/.config/freshdesk/`, never in the repo):
   ```sh
   mkdir -p ~/.config/freshdesk
   printf '%s' 'YOURACCOUNT.freshdesk.com' > ~/.config/freshdesk/domain
   printf '%s' 'YOUR_API_KEY'              > ~/.config/freshdesk/key
   chmod 600 ~/.config/freshdesk/key
   ```
   Your API key is in Freshdesk → profile picture → **Your API Key**.
   (Alternatively export `FRESHDESK_DOMAIN` / `FRESHDESK_API_KEY`.)

3. **Test from the terminal:**
   ```sh
   python3 fd_list.py "Webapp"
   ```
   You should see a scored list. If not, the error tells you what's missing.

4. **Generate your notes**, positioning them on screen. The first argument is
   the note's **name** (its title, filename, and saved position key); by default
   it's also the filter, but `--query` can override that:
   ```sh
   # plain project note (name == filter)
   python3 make_widget.py "Webapp"       --top 40 --left 40
   python3 make_widget.py "BILLING-ACME" --top 40 --left 430 --accent "#e07a3f"

   # name different from the filter
   python3 make_widget.py "Lublin" --query "up.lublin" --left 820

   # "Other" — tickets matching NONE of the listed filters
   python3 make_widget.py "Other" --exclude "Webapp" "BILLING-ACME" "Lublin" --top 360

   # "Recently reported" — newest first, ignoring the priority score
   python3 make_widget.py "Recent" --recent --left 1210
   ```
   Once installed, **drag a note with the mouse** to reposition it — the spot is
   remembered (localStorage), so refreshes and reboots keep it in place. Clicking
   a ticket row still opens it in the browser.

   Each note's header has three controls (they don't trigger dragging):
   - **⟳ refresh** — re-runs that note's query on demand (via Übersicht's `run`),
     without waiting for the 5-minute cycle;
   - **▾ / ▸ collapse** — shrinks the note to just its title + counts strip; click
     again to expand;
   - **✕ hide** — collapses the whole note to a small **📌 pin**; click the pin to
     bring it back.

   Drag the **bottom edge** of a note to set a fixed height (the ticket list then
   scrolls inside); **double-click** that edge to go back to auto-height. Collapse,
   hide and height are all remembered per note in localStorage, just like position.

   To regenerate every note at once after a template change, see
   [Regenerating and installing](#regenerating-and-installing) below.

5. **Install the widgets** into Übersicht:
   ```sh
   ./install-widgets.sh
   ```
   (or copy `widgets/*.jsx` into Übersicht's widgets folder, then ⌘R to refresh).

## Regenerating and installing

Notes flow through three stages — **source → generated files → live Übersicht**:

```
make_widget.py        ./regen.sh         widgets/*.jsx       ./install-widgets.sh    Übersicht
(template, in repo) ─────────────────► (generated,      ──────────────────────► ~/Library/.../widgets/
                     stamps out 6        git-ignored)         copies the files    (what shows on screen)
                     .jsx files
```

`make_widget.py` is the single source of truth (the template). The generated
`widgets/*.jsx` are **git-ignored** — they contain machine-specific absolute
paths, so everyone generates their own.

### `regen.sh` — build the notes from the template

Runs `make_widget.py` once per note with each note's remembered arguments
(name, position, accent, filter), overwriting `widgets/freshdesk-*.jsx` from the
**current** template. It does **not** touch Übersicht — it only produces files in
the repo. It doubles as the list of your notes; add a line to add a note. The
`--top/--left` values are only **starting** positions: once you've dragged a note,
the position saved in localStorage wins, so regenerating never moves notes you've
already placed.

### `install-widgets.sh` — copy them into Übersicht

Copies `widgets/freshdesk-*.jsx` into Übersicht's widgets folder
(`~/Library/Application Support/Übersicht/widgets`). If that folder doesn't exist
(Übersicht not installed/launched), it stops with a message. After copying, press
**⌘R** in Übersicht to reload.

Generation and deployment are kept separate on purpose: you can regenerate and
review the files in the repo before anything reaches your live desktop.

### When to run what

- Changed the **template** (`make_widget.py`) or the args in `regen.sh`:
  `./regen.sh && ./install-widgets.sh`, then **⌘R**.
- Adding a **new** note: add a line to `regen.sh` (or run `make_widget.py "Name"
  --top … --left …` once), then `./install-widgets.sh` + **⌘R**.
- Changed only the ticket-fetching logic (`freshdesk_lib.py` / `fd_list.py`): no
  regeneration needed — just **⌘R** (or the note's **⟳** button), since the widget
  calls those scripts live.

Mnemonic: **`regen` = build the files, `install` = put them in Übersicht, ⌘R = show them.**

## Notes & limits

- Clicking a row opens the ticket in your browser (the widget enables pointer
  events, so it captures clicks over its area).
- "First response sent" is approximated by an unassigned responder — fine for a
  single-agent account; refine in `score_open` if you run a team.
- "Client is waiting on you" detection (last message direction) is intentionally
  left out of the always-on widget to keep it fast; do that nuance interactively.

## License

MIT — see [LICENSE](LICENSE).
