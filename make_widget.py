#!/usr/bin/env python3
"""Generator samodzielnych widgetów Übersicht (jeden plik = jedna karteczka).

Użycie:
    python3 make_widget.py "Webapp"           --top 40  --left 40
    python3 make_widget.py "BILLING-ACME"     --top 40  --left 430 --accent "#e07a3f"

Powstaje plik widgets/freshdesk-<slug>.jsx. Skopiuj go (albo cały katalog
widgets/) do katalogu widgetów Übersicht — patrz README.
"""

import argparse
import re
import sys
from pathlib import Path

# Wykrywane automatycznie — żeby projekt był przenośny (zero zaszytych ścieżek).
PYTHON = sys.executable
PROJECT_DIR = str(Path(__file__).resolve().parent)

TEMPLATE = r"""// AUTO-GENEROWANE przez make_widget.py — edytuj generator, nie ten plik.
// Karteczka Freshdesk dla projektu: __PROJECT__

export const refreshFrequency = 300000; // 5 min

export const command =
  `cd __PROJECT_DIR__ && __PYTHON__ fd_list.py "__PROJECT__" --json`;

export const className = `
  top: __TOP__px;
  left: __LEFT__px;
  width: 360px;
  pointer-events: auto;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: #2b2b2b;
  background: #fff8c4;
  border-radius: 10px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.28);
  padding: 12px 14px;
  font-size: 12px;
  line-height: 1.45;
`;

const hdr = { borderLeft: "4px solid __ACCENT__", paddingLeft: 8, marginBottom: 8 };
const title = { fontWeight: 700, fontSize: 14, letterSpacing: 0.3 };
const sub = { fontSize: 11, opacity: 0.7 };
const row = {
  display: "block", textDecoration: "none", color: "inherit",
  padding: "2px 0", borderTop: "1px solid rgba(0,0,0,0.07)", whiteSpace: "nowrap",
  overflow: "hidden", textOverflow: "ellipsis",
};
const idc = { fontVariantNumeric: "tabular-nums", opacity: 0.55, marginRight: 6 };
const pend = { marginTop: 8, paddingTop: 6, borderTop: "1px dashed rgba(0,0,0,0.25)", fontSize: 11 };

const trunc = (s, n = 42) => (s.length <= n ? s : s.slice(0, n - 1) + "…");

export const render = ({ output, error }) => {
  if (error) return <div style={hdr}>⚠️ błąd: {String(error)}</div>;
  let d;
  try { d = JSON.parse(output); }
  catch (e) {
    return (
      <div style={hdr}>
        <div style={title}>__PROJECT__</div>
        <div style={sub}>Brak danych — sprawdź klucz API (~/.config/freshdesk/key).</div>
      </div>
    );
  }
  const c = d.counts;
  return (
    <div>
      <div style={hdr}>
        <div style={title}>__PROJECT__</div>
        <div style={sub}>
          🔴 {c.open} open ({c.open_sla} po SLA) · 🟡 {c.pending} pending
        </div>
      </div>
      {d.open.length === 0 && <div style={sub}>brak otwartych 🎉</div>}
      {d.open.map((r) => (
        <a style={row} href={r.url} title={r.subject}>
          <span style={idc}>#{r.id}</span>
          {r.flags.join("")} {trunc(r.subject)}
        </a>
      ))}
      {d.pending.filter((r) => r.bucket !== "fresh").length > 0 && (
        <div style={pend}>
          {d.pending.filter((r) => r.bucket !== "fresh").map((r) => (
            <a style={row} href={r.url} title={r.subject}>
              <span style={idc}>{r.bucket === "close" ? "🗑" : "🔔"} #{r.id}</span>
              {trunc(r.subject)}
            </a>
          ))}
        </div>
      )}
      <div style={{ ...sub, marginTop: 8, textAlign: "right" }}>
        {d.generated_at.slice(11, 16)}
      </div>
    </div>
  );
};
"""


def slug(project: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", project.lower()).strip("-")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--left", type=int, default=40)
    ap.add_argument("--accent", default="#3f7ae0")
    a = ap.parse_args()

    content = (
        TEMPLATE.replace("__PROJECT_DIR__", PROJECT_DIR)
        .replace("__PYTHON__", PYTHON)
        .replace("__PROJECT__", a.project)
        .replace("__TOP__", str(a.top))
        .replace("__LEFT__", str(a.left))
        .replace("__ACCENT__", a.accent)
    )
    out = Path(__file__).parent / "widgets" / f"freshdesk-{slug(a.project)}.jsx"
    out.write_text(content, encoding="utf-8")
    print(f"zapisano {out}")


if __name__ == "__main__":
    main()
