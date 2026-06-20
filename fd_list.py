#!/usr/bin/env python3
"""CLI dla widgetu Übersicht i do testów w terminalu.

Użycie:
    python3 fd_list.py "Webapp"                       # filtr (tekst, test)
    python3 fd_list.py "Webapp" --json                # JSON dla widgetu
    python3 fd_list.py                                 # bez filtra = wszystko
    python3 fd_list.py --exclude "Webapp" "ACME"      # 'pozostałe' (nie pasujące)
    python3 fd_list.py --recent                        # 'ostatnio zgłoszone'
"""

import argparse
import json

import freshdesk_lib as fd


def _truncate(s: str, n: int = 58) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _text(data: dict) -> str:
    c = data["counts"]
    head = f"🔴 {c['open']} open ({c['open_sla']} po SLA)"
    if c["pending"]:
        head += f" · 🟡 {c['pending']} pending ({c['remind']} 🔔, {c['close']} 🗑)"
    lines = [
        f"Freshdesk — [{data['project']}]   {data['generated_at']}",
        head,
        "",
    ]
    tier_labels = {0: "⏰ Po SLA", 1: "⌛ Termin <48h", 2: "Pozostałe"}
    grouped = data.get("grouped")
    last_tier = object()
    for r in data["open"]:
        if grouped and r.get("tier") != last_tier:
            last_tier = r.get("tier")
            lines.append(f"— {tier_labels.get(last_tier, '—')} —")
        flags = " ".join(r["flags"])
        mark = "💬 " if r.get("from_pending") else ""
        lines.append(f"  #{r['id']:<4} {flags:14} {mark}{_truncate(r['subject'])}  ·{r['age_days']:.0f}d")
    if data["pending"]:
        lines.append("")
        icon = {"close": "🗑", "remind": "🔔", "fresh": "·"}
        for r in data["pending"]:
            d = r.get("silence_days") or 0
            lines.append(f"  {icon[r['bucket']]} #{r['id']} {_truncate(r['subject'])}  · klient {d:.0f}d")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Lista zgłoszeń z Freshdeska (scoring + filtr).")
    ap.add_argument("project", nargs="?", default=None, help="filtr włączający, np. 'BPP' / 'APOZ-ATOM'")
    ap.add_argument(
        "--exclude",
        nargs="*",
        metavar="FILTR",
        help="pokaż tylko zgłoszenia NIE pasujące do żadnego z tych filtrów ('pozostałe')",
    )
    ap.add_argument("--recent", action="store_true", help="sortuj wg daty zgłoszenia (najnowsze u góry)")
    ap.add_argument("--limit", type=int, default=None, help="przytnij listę otwartych do N")
    ap.add_argument("--json", action="store_true", help="wyjście JSON (dla widgetu Übersicht)")
    a = ap.parse_args()

    limit = a.limit if a.limit is not None else (12 if a.recent else None)
    data = fd.build(project=a.project, exclude=a.exclude, recent=a.recent, limit=limit)

    if a.json:
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(_text(data))


if __name__ == "__main__":
    main()
