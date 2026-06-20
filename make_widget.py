#!/usr/bin/env python3
"""Generator samodzielnych widgetów Übersicht (jeden plik = jedna karteczka).

Pierwszy argument to NAZWA karteczki (tytuł + nazwa pliku + klucz pozycji).
Domyślnie jest też filtrem; filtr można nadpisać przez --query.

Każda karteczka ma w nagłówku trzy przyciski:
    ⟳  odśwież teraz (uruchamia komendę na żądanie przez `run` z Übersicht),
    ▾/▸ zwiń do nagłówka / rozwiń,
    ✕  ukryj — zostaje tylko pinezka „📌 NAZWA"; klik w nią przywraca.
Dolną krawędź listy można chwycić i zmienić wysokość (dwuklik = auto).
Stan (zwinięcie / ukrycie / wysokość) oraz pozycja są zapamiętane w
localStorage — przeżywają odświeżenie i restart.

Użycie:
    # zwykła karteczka projektu (nazwa = filtr):
    python3 make_widget.py "Webapp"        --top 40  --left 40
    python3 make_widget.py "BILLING-ACME"  --top 40  --left 430 --accent "#e07a3f"

    # nazwa inna niż filtr:
    python3 make_widget.py "Lublin" --query "up.lublin" --left 820

    # 'pozostałe' — zgłoszenia NIE pasujące do żadnego z podanych filtrów:
    python3 make_widget.py "Pozostałe" --exclude "Webapp" "BILLING-ACME" --top 360

    # 'ostatnio zgłoszone' — wg daty zgłoszenia, najnowsze u góry:
    python3 make_widget.py "Ostatnio" --recent --left 1210

Powstaje plik widgets/freshdesk-<slug>.jsx. Skopiuj go (albo cały katalog
widgets/) do katalogu widgetów Übersicht — patrz README. Po zmianie tego
generatora wszystkie istniejące karteczki przegenerujesz przez ./regen.sh.
"""

import argparse
import re
import sys
from pathlib import Path

# Wykrywane automatycznie — żeby projekt był przenośny (zero zaszytych ścieżek).
PYTHON = sys.executable
PROJECT_DIR = str(Path(__file__).resolve().parent)

TEMPLATE = r"""// AUTO-GENEROWANE przez make_widget.py — edytuj generator, nie ten plik.
// Karteczka Freshdesk: __LABEL__

import { run } from "uebersicht";

export const refreshFrequency = 300000; // 5 min (Übersicht odświeża komendę cyklicznie)

export const command = `__COMMAND__`;

// Wrapper trzymamy w 0,0 — realną pozycję i wygląd ustawiamy na korzeniu
// (position: fixed), dzięki czemu karteczkę można przeciągać myszą.
export const className = `top: 0; left: 0;`;

const POS_KEY = "fdpos-__SLUG__"; // pozycja (przeciąganie) — jak dotychczas
const UI_KEY = "fdui-__SLUG__";   // zwinięcie / ukrycie / wysokość listy
const DEFAULT_POS = { x: __LEFT__, y: __TOP__ };
const MIN_BODY = 48;              // minimalna wysokość listy przy zmianie rozmiaru

// --- trwały stan UI (localStorage) -----------------------------------------
function loadUI() {
  try { return JSON.parse(localStorage.getItem(UI_KEY)) || {}; }
  catch (e) { return {}; } // brak/zepsuty wpis — startujemy z domyślnych
}
function saveUI(patch) {
  const next = { ...loadUI(), ...patch };
  try { localStorage.setItem(UI_KEY, JSON.stringify(next)); }
  catch (e) { /* tryb prywatny / brak miejsca — stan zostaje tylko w pamięci */ }
}

// --- stan widgetu (model Übersicht: initialState + updateState) -------------
const _ui = loadUI();
export const initialState = {
  output: "",
  error: null,
  busy: false,
  collapsed: !!_ui.collapsed,
  hidden: !!_ui.hidden,
  height: typeof _ui.height === "number" ? _ui.height : null,
};

export const updateState = (event, prev) => {
  switch (event.type) {
    case "FD/SET":       return { ...prev, ...event.patch };
    case "FD/BUSY":      return { ...prev, busy: true };
    case "FD/REFRESHED": return { ...prev, busy: false, output: event.output, error: null };
    case "FD/ERROR":     return { ...prev, busy: false, error: event.error };
    default:
      // Wbudowane zdarzenie po zakończeniu `command` niesie output/error
      // (jego typ bywa "UB/COMMAND_RAN" — rozpoznajemy je po obecności pól).
      if ("output" in event || "error" in event) {
        return { ...prev, busy: false, output: event.output, error: event.error };
      }
      return prev;
  }
};

// --- akcje ------------------------------------------------------------------
function setUI(dispatch, patch) {
  saveUI(patch);
  dispatch({ type: "FD/SET", patch });
}
function refreshNow(dispatch) {
  dispatch({ type: "FD/BUSY" });
  run(command)
    .then((output) => dispatch({ type: "FD/REFRESHED", output }))
    .catch((err) => dispatch({ type: "FD/ERROR", error: String(err) }));
}

// --- przeciąganie pozycji (+ wykrycie „tapnięcia" do przywrócenia pinezki) --
function initDrag(el, onTap) {
  if (!el) return;
  if (onTap !== undefined) el.__fdTap = onTap; // tap = klik bez przeciągnięcia
  if (el.__fdInit) return;
  el.__fdInit = true;
  let pos;
  try { pos = JSON.parse(localStorage.getItem(POS_KEY)); } catch (e) { pos = null; }
  if (!pos) pos = { ...DEFAULT_POS };
  const apply = () => { el.style.left = pos.x + "px"; el.style.top = pos.y + "px"; };
  apply();
  let drag = false, sx = 0, sy = 0, ox = 0, oy = 0;
  el.addEventListener("mousedown", (e) => {
    if (e.target.closest("a")) return;             // klik w link działa normalnie
    if (e.target.closest("[data-nodrag]")) return; // przyciski / uchwyt nie przeciągają
    drag = true; el.__fdMoved = false;
    sx = e.clientX; sy = e.clientY; ox = pos.x; oy = pos.y;
    el.style.cursor = "grabbing";
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!drag) return;
    pos.x = ox + (e.clientX - sx);
    pos.y = oy + (e.clientY - sy);
    if (Math.abs(e.clientX - sx) + Math.abs(e.clientY - sy) > 4) el.__fdMoved = true;
    apply();
  });
  window.addEventListener("mouseup", () => {
    if (!drag) return;
    drag = false;
    el.style.cursor = "grab";
    localStorage.setItem(POS_KEY, JSON.stringify(pos));
    if (!el.__fdMoved && el.__fdTap) el.__fdTap(); // tapnięcie bez ruchu = akcja
  });
}

// --- zmiana wysokości listy od dołu ----------------------------------------
let bodyEl = null;
const bodyRef = (el) => { if (el) bodyEl = el; };
function startResize(e, dispatch) {
  e.preventDefault();
  // Korzeń karteczki (rodzic uchwytu). Pozycję (top/left) trzymamy ZABLOKOWANĄ
  // na czas całego gestu — dzięki temu zmiana wysokości listy NIE przesuwa
  // karteczki w górę/dół (rośnie tylko dół, lewy-górny róg stoi w miejscu).
  const root = e.currentTarget ? e.currentTarget.parentElement : null;
  const lockTop = root ? root.style.top : "";
  const lockLeft = root ? root.style.left : "";
  const pin = () => {
    if (!root) return;
    if (lockTop) root.style.top = lockTop;
    if (lockLeft) root.style.left = lockLeft;
  };
  const startY = e.clientY;
  const startH = bodyEl ? bodyEl.offsetHeight : 0;
  let lastH = startH, moved = false;
  if (bodyEl) bodyEl.style.overflowY = "auto";
  const move = (ev) => {
    moved = true;
    lastH = Math.max(MIN_BODY, startH + (ev.clientY - startY));
    if (bodyEl) bodyEl.style.maxHeight = lastH + "px";
    pin(); // utrzymaj pozycję — zmieniamy wyłącznie wysokość
  };
  const up = () => {
    window.removeEventListener("mousemove", move);
    window.removeEventListener("mouseup", up);
    pin();
    if (moved) setUI(dispatch, { height: lastH }); // czysty klik nie zmienia rozmiaru
  };
  window.addEventListener("mousemove", move);
  window.addEventListener("mouseup", up);
}

// --- style ------------------------------------------------------------------
const rootStyle = {
  position: "fixed", width: "360px", pointerEvents: "auto", cursor: "grab",
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  color: "#2b2b2b", background: "#fff8c4", borderRadius: "10px",
  boxShadow: "0 6px 20px rgba(0,0,0,0.28)", padding: "12px 14px",
  fontSize: "12px", lineHeight: 1.45,
};
const pinStyle = {
  position: "fixed", pointerEvents: "auto", cursor: "grab",
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  color: "#2b2b2b", background: "#fff8c4", borderRadius: "8px",
  boxShadow: "0 4px 12px rgba(0,0,0,0.28)", padding: "5px 10px",
  fontSize: "12px", fontWeight: 700, whiteSpace: "nowrap", userSelect: "none",
};
const hdr = { borderLeft: "4px solid __ACCENT__", paddingLeft: 8, marginBottom: 8 };
const hdrRow = { display: "flex", alignItems: "center", gap: 8 };
const title = {
  fontWeight: 700, fontSize: 14, letterSpacing: 0.3,
  flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
};
const sub = { fontSize: 11, opacity: 0.7 };
const ctlWrap = { display: "flex", alignItems: "center", gap: 9, flex: "0 0 auto" };
const ctl = { cursor: "pointer", opacity: 0.6, fontSize: 16, lineHeight: 1, userSelect: "none" };
const row = {
  display: "block", textDecoration: "none", color: "inherit",
  padding: "2px 0", borderTop: "1px solid rgba(0,0,0,0.07)", whiteSpace: "nowrap",
  overflow: "hidden", textOverflow: "ellipsis",
};
const idc = { fontVariantNumeric: "tabular-nums", opacity: 0.55, marginRight: 6 };
const pend = { marginTop: 8, paddingTop: 6, borderTop: "1px dashed rgba(0,0,0,0.25)", fontSize: 11 };
const handle = { height: 7, marginTop: 6, borderRadius: 5, cursor: "ns-resize", background: "rgba(0,0,0,0.10)" };

const trunc = (s, n = 42) => (s.length <= n ? s : s.slice(0, n - 1) + "…");

// --- render -----------------------------------------------------------------
export const render = (state, dispatch) => {
  const { output, error, busy, collapsed, hidden, height } = state;

  // Ukryta: tylko pinezka. Klik (bez przeciągnięcia) przywraca; nadal przeciągalna.
  if (hidden) {
    return (
      <div style={pinStyle} ref={(el) => initDrag(el, () => setUI(dispatch, { hidden: false }))}>
        📌 __LABEL__
      </div>
    );
  }

  let d = null;
  if (!error) { try { d = JSON.parse(output); } catch (e) { d = null; } }
  const c = d && d.counts;

  const controls = (
    <span style={ctlWrap}>
      <span style={ctl} data-nodrag="1" title="Odśwież teraz"
            onClick={() => refreshNow(dispatch)}>{busy ? "⏳" : "⟳"}</span>
      <span style={ctl} data-nodrag="1" title={collapsed ? "Rozwiń" : "Zwiń"}
            onClick={() => setUI(dispatch, { collapsed: !collapsed })}>{collapsed ? "▸" : "▾"}</span>
      <span style={ctl} data-nodrag="1" title="Ukryj (zostanie pinezka)"
            onClick={() => setUI(dispatch, { hidden: true })}>✕</span>
    </span>
  );

  const countsLine = c
    ? <span>🔴 {c.open} open ({c.open_sla} po SLA) · 🐌 {c.pending} klient</span>
    : <span>{error ? "⚠️ błąd" : "—"}</span>;

  // Zwinięta: tylko pasek nagłówka (tytuł + liczniki + przyciski).
  if (collapsed) {
    return (
      <div style={{ ...rootStyle, padding: "8px 14px" }} ref={(el) => initDrag(el, null)}>
        <div style={{ ...hdr, marginBottom: 0, ...hdrRow }}>
          <span style={title}>__LABEL__</span>
          <span style={{ ...sub, flex: "0 0 auto" }}>{countsLine}</span>
          {controls}
        </div>
      </div>
    );
  }

  // Pełna karteczka.
  return (
    <div style={rootStyle} ref={(el) => initDrag(el, null)}>
      <div style={hdr}>
        <div style={hdrRow}>
          <div style={title}>__LABEL__</div>
          {controls}
        </div>
        <div style={sub}>{countsLine}</div>
      </div>

      <div ref={bodyRef}
           style={{ maxHeight: height ? height + "px" : "none",
                    overflowY: height ? "auto" : "visible" }}>
        {error && <div style={sub}>⚠️ błąd: {String(error)}</div>}
        {!error && !d && (
          <div style={sub}>Brak danych — sprawdź klucz API (~/.config/freshdesk/key).</div>
        )}
        {!error && d && d.open && d.open.length === 0 && (
          <div style={sub}>brak otwartych 🎉</div>
        )}
        {!error && d && d.open && d.open.map((r) => (
          <a style={row} href={r.url} title={r.subject} key={r.id}>
            <span style={idc}>#{r.id}</span>{r.from_pending ? "💬 " : ""}{r.flags.join("")} {trunc(r.subject)}
          </a>
        ))}
        {!error && d && d.pending && d.pending.length > 0 && (
          <div style={pend}>
            {d.pending.map((r) => (
              <a style={row} href={r.url} title={r.subject} key={r.id}>
                <span style={idc}>🐌 #{r.id}</span>{trunc(r.subject, 30)}{" "}
                <span style={{ opacity: 0.55 }}>klient {Math.round(r.silence_days || 0)}d</span>
              </a>
            ))}
          </div>
        )}
        {d && d.generated_at && (
          <div style={{ ...sub, marginTop: 8, textAlign: "right" }}>{d.generated_at.slice(11, 16)}</div>
        )}
      </div>

      <div style={handle} data-nodrag="1"
           title="Przeciągnij = zmień wysokość · dwuklik = auto"
           onMouseDown={(e) => startResize(e, dispatch)}
           onDoubleClick={() => {
             setUI(dispatch, { height: null });
             if (bodyEl) { bodyEl.style.maxHeight = "none"; bodyEl.style.overflowY = "visible"; }
           }} />
    </div>
  );
};
"""


def slug(project: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", project.lower()).strip("-")


def build_command(a) -> str:
    """Złóż komendę fd_list dla widgetu z opcji generatora."""
    fd_args: list[str] = []
    if a.recent:
        fd_args.append("--recent")
    elif a.exclude:
        fd_args.append("--exclude")
        fd_args += [f'"{e}"' for e in a.exclude]
    else:
        query = a.query if a.query is not None else a.label
        if query:
            fd_args.append(f'"{query}"')
    if a.limit is not None:
        fd_args += ["--limit", str(a.limit)]
    fd_args.append("--json")
    return f"cd {PROJECT_DIR} && {PYTHON} fd_list.py " + " ".join(fd_args)


def build_widget(a) -> str:
    """Wyrenderuj treść pliku .jsx karteczki z opcji generatora."""
    return (
        TEMPLATE.replace("__COMMAND__", build_command(a))
        .replace("__SLUG__", slug(a.label))
        .replace("__LABEL__", a.label)
        .replace("__TOP__", str(a.top))
        .replace("__LEFT__", str(a.left))
        .replace("__ACCENT__", a.accent)
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Generator karteczek Übersicht dla Freshdeska.")
    ap.add_argument("label", help="nazwa karteczki: tytuł + nazwa pliku + klucz pozycji")
    ap.add_argument("--query", default=None, help="filtr fd_list (domyślnie = label), np. 'APOZ-ATOM'")
    ap.add_argument(
        "--exclude",
        nargs="*",
        metavar="FILTR",
        help="karteczka 'pozostałe': pokaż NIE pasujące do żadnego z tych filtrów",
    )
    ap.add_argument("--recent", action="store_true", help="karteczka 'ostatnio zgłoszone' (wg daty)")
    ap.add_argument("--limit", type=int, default=None, help="przytnij listę otwartych do N")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--left", type=int, default=40)
    ap.add_argument("--accent", default="#3f7ae0")
    a = ap.parse_args()

    content = build_widget(a)
    out = Path(__file__).parent / "widgets" / f"freshdesk-{slug(a.label)}.jsx"
    out.write_text(content, encoding="utf-8")
    print(f"zapisano {out}")


if __name__ == "__main__":
    main()
