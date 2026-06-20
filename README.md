# freshdesk-stickies

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

4. **Generate your notes** (one per project), positioning them on screen:
   ```sh
   python3 make_widget.py "Webapp"       --top 40 --left 40
   python3 make_widget.py "BILLING-ACME" --top 40 --left 430 --accent "#e07a3f"
   ```

5. **Install the widgets** into Übersicht:
   ```sh
   ./install-widgets.sh
   ```
   (or copy `widgets/*.jsx` into Übersicht's widgets folder, then ⌘R to refresh).

## Notes & limits

- Clicking a row opens the ticket in your browser (the widget enables pointer
  events, so it captures clicks over its area).
- "First response sent" is approximated by an unassigned responder — fine for a
  single-agent account; refine in `score_open` if you run a team.
- "Client is waiting on you" detection (last message direction) is intentionally
  left out of the always-on widget to keep it fast; do that nuance interactively.

## License

MIT — see [LICENSE](LICENSE).
