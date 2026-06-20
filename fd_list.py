#!/usr/bin/env python3
"""CLI dla widgetu Übersicht i do testów w terminalu.

Użycie:
    python3 fd_list.py "Webapp"          # ładny wydruk tekstowy (test)
    python3 fd_list.py "Webapp" --json   # JSON dla widgetu Übersicht
    python3 fd_list.py                   # bez filtra = wszystko
"""

import json
import sys

import freshdesk_lib as fd


def _truncate(s: str, n: int = 58) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _text(data: dict) -> str:
    c = data["counts"]
    lines = [
        f"Freshdesk — [{data['project']}]   {data['generated_at']}",
        f"🔴 {c['open']} open ({c['open_sla']} po SLA) · "
        f"🟡 {c['pending']} pending ({c['remind']} przypomnij, {c['close']} zamknij)",
        "",
    ]
    for i, r in enumerate(data["open"], 1):
        flags = " ".join(r["flags"])
        lines.append(f"{i:2}. #{r['id']:<4} {flags:14} {_truncate(r['subject'])}  ·{r['age_days']:.0f}d")
    if data["pending"]:
        lines.append("")
        icon = {"close": "🗑", "remind": "🔔", "fresh": "·"}
        for r in data["pending"]:
            lines.append(f"  {icon[r['bucket']]} #{r['id']} {_truncate(r['subject'])}  ·{r['age_days']:.0f}d")
    return "\n".join(lines)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv[1:]
    project = args[0] if args else None

    data = fd.build(project)
    if as_json:
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(_text(data))


if __name__ == "__main__":
    main()
