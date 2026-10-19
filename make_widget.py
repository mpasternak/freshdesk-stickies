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
    python3 make_widget.py "Firma" --query "firma.example" --left 820

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
const LAST_KEY = "fdlast-__SLUG__"; // ostatnie udane dane — pokazywane, gdy nie ma sieci
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

// --- ostatnie udane dane (fallback offline) ---------------------------------
function parseData(output) {
  try { const d = JSON.parse(output); return d && d.counts ? d : null; }
  catch (e) { return null; } // nie-JSON (np. komunikat błędu) = brak świeżych danych
}
function loadLast() {
  try { return JSON.parse(localStorage.getItem(LAST_KEY)); }
  catch (e) { return null; } // brak/zepsuty wpis — po prostu nie mamy kopii
}
function saveLast(d) {
  try { localStorage.setItem(LAST_KEY, JSON.stringify(d)); }
  catch (e) { /* brak miejsca — kopia zostaje tylko w pamięci (state.last) */ }
}
// Wynik komendy: udane dane zapamiętujemy, przy błędzie zostaje poprzednia kopia.
function withResult(prev, output, error) {
  const d = error ? null : parseData(output);
  if (d) saveLast(d);
  return { ...prev, busy: false, output, error, last: d || prev.last };
}

// --- motywy kolorystyczne (🎨 w nagłówku otwiera paletę 6×6; wybór zapamiętany)
// Rząd 1: odcienie neutralne; dalej kolumna = barwa, rząd = ton (głęboki → pastelowy).
const NEUTRALS = [
  ["czarny", "rgba(0,0,0,0.88)", "#f0f0f0"],
  ["grafit", "rgba(28,28,30,0.84)", "#ececec"],
  ["łupek", "rgba(58,64,74,0.88)", "#eef1f5"],
  ["stal", "rgba(120,126,136,0.90)", "#ffffff"],
  ["perła", "rgba(222,224,228,0.94)", "#1d1d1f"],
  ["biały", "rgba(250,250,252,0.94)", "#1d1d1f"],
];
const HUES = [
  ["czerwony", 355], ["pomarańczowy", 26], ["żółty", 50], ["zielony", 145], ["niebieski", 215], ["fioletowy", 275],
];
// [nazwa tonu, nasycenie %, jasność %, krycie, kolor tekstu]
const TONES = [
  ["głęboki", 45, 14, 0.9, "#f4f4f4"],
  ["ciemny", 40, 24, 0.9, "#f4f4f4"],
  ["średni", 42, 38, 0.92, "#ffffff"],
  ["jasny", 60, 76, 0.95, "#1d1d1f"],
  ["pastelowy", 70, 90, 0.95, "#1d1d1f"],
];
const THEMES = {};
NEUTRALS.forEach(([name, bg, fg]) => { THEMES[name] = { bg, fg }; });
TONES.forEach(([tone, s, l, a, fg]) => HUES.forEach(([hue, h]) => {
  THEMES[`${hue} ${tone}`] = { bg: `hsla(${h}, ${s}%, ${l}%, ${a})`, fg };
}));
const THEME_NAMES = Object.keys(THEMES); // kolejność = rzędy palety 6×6
// Nazwy z poprzedniej, mniejszej palety → najbliższy odpowiednik.
const THEME_ALIASES = {
  ciemny: "grafit", granat: "niebieski głęboki", niebieski: "niebieski ciemny", morski: "zielony głęboki",
  zielony: "zielony ciemny", oliwka: "żółty głęboki", "brąz": "pomarańczowy głęboki", bordo: "czerwony głęboki",
  "śliwka": "fioletowy głęboki", fiolet: "fioletowy ciemny", karteczka: "żółty pastelowy",
  "mięta": "zielony pastelowy", "błękit": "niebieski pastelowy", "róż": "czerwony pastelowy", jasny: "biały",
};
const DEFAULT_THEME = "__THEME__";
const resolveTheme = (name) => (THEMES[name] ? name : THEME_ALIASES[name]);
const themeOf = (name) => THEMES[resolveTheme(name)] || THEMES[resolveTheme(DEFAULT_THEME)] || THEMES.grafit;
// Linie/tła pomocnicze liczone z koloru tekstu — pasują do każdego motywu.
const mix = (pct) => `color-mix(in srgb, currentColor ${pct}%, transparent)`;

// Paleta 6×6 pod przyciskiem 🎨 (pozycja względem korzenia karteczki).
const pickerBox = {
  position: "absolute", top: 30, right: 10, zIndex: 10, padding: 6, borderRadius: 8,
  display: "grid", gridTemplateColumns: "repeat(6, 18px)", gap: 4,
  boxShadow: "0 6px 18px rgba(0,0,0,0.45)", border: "1px solid " + mix(20), cursor: "default",
};
function themePicker(current, onPick) {
  const cur = resolveTheme(current);
  return (
    <div style={{ ...pickerBox, background: themeOf(current).bg }} data-nodrag="1">
      {THEME_NAMES.map((name) => (
        <span key={name} title={name} data-nodrag="1" onClick={() => onPick(name)}
              style={{ width: 18, height: 18, borderRadius: 4, cursor: "pointer", background: THEMES[name].bg,
                       boxShadow: name === cur ? "0 0 0 2px " + THEMES[name].fg + ", 0 0 0 3px rgba(0,0,0,0.5)"
                                              : "inset 0 0 0 1px rgba(127,127,127,0.5)" }} />
      ))}
    </div>
  );
}

// --- stan widgetu (model Übersicht: initialState + updateState) -------------
const _ui = loadUI();
export const initialState = {
  output: "",
  error: null,
  busy: false,
  last: loadLast(),
  collapsed: !!_ui.collapsed,
  hidden: !!_ui.hidden,
  height: typeof _ui.height === "number" ? _ui.height : null,
  theme: resolveTheme(_ui.theme) || DEFAULT_THEME,
};

export const updateState = (event, prev) => {
  switch (event.type) {
    case "FD/SET":       return { ...prev, ...event.patch };
    case "FD/BUSY":      return { ...prev, busy: true };
    case "FD/REFRESHED": return withResult(prev, event.output, null);
    case "FD/ERROR":     return withResult(prev, "", event.error);
    default:
      // Wbudowane zdarzenie po zakończeniu `command` niesie output/error
      // (jego typ bywa "UB/COMMAND_RAN" — rozpoznajemy je po obecności pól).
      if ("output" in event || "error" in event) {
        return withResult(prev, event.output, event.error);
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

// --- wyciąganie na wierzch: wciśnięta karteczka idzie nad pozostałe -------
// Wszystkie widgety Übersicht leżą na jednej stronie i dzielą localStorage, więc
// wspólny licznik "sticky-z-top" daje każdej wciśniętej karteczce najwyższy
// z-index. Własny zapisujemy pod Z_KEY — kolejność przeżywa odświeżenie.
const Z_KEY = POS_KEY + ":z";
function initRaise(el) {
  let z = 0;
  try { z = parseInt(localStorage.getItem(Z_KEY), 10) || 0; }
  catch (e) { z = 0; } // brak localStorage — kolejność tylko do odświeżenia
  if (z) el.style.zIndex = String(z);
  el.addEventListener("mousedown", () => {
    let top = 0;
    try { top = parseInt(localStorage.getItem("sticky-z-top"), 10) || 0; }
    catch (e) { top = 0; } // jw. — liczymy od zera
    if (top && String(top) === el.style.zIndex) return; // już jest na wierzchu
    el.style.zIndex = String(top + 1);
    try {
      localStorage.setItem("sticky-z-top", String(top + 1));
      localStorage.setItem(Z_KEY, String(top + 1));
    } catch (e) { /* brak miejsca — kolejność zostaje tylko do odświeżenia */ }
  }, true); // capture: działa też przy kliknięciu w przycisk / link
}

// --- przeciąganie pozycji (+ wykrycie „tapnięcia" do przywrócenia pinezki) --
function initDrag(el, onTap) {
  if (!el) return;
  if (onTap !== undefined) el.__fdTap = onTap; // tap = klik bez przeciągnięcia
  if (el.__fdInit) return;
  el.__fdInit = true;
  initRaise(el);
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
  border: "1px solid " + mix(12), borderRadius: "10px",
  boxShadow: "0 8px 24px rgba(0,0,0,0.35)", padding: "12px 14px",
  fontSize: "12px", lineHeight: 1.45,
};
const pinStyle = {
  position: "fixed", pointerEvents: "auto", cursor: "grab",
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  border: "1px solid " + mix(12), borderRadius: "8px",
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
  padding: "2px 0", borderTop: "1px solid " + mix(8), whiteSpace: "nowrap",
  overflow: "hidden", textOverflow: "ellipsis",
};
const idc = { fontVariantNumeric: "tabular-nums", opacity: 0.55, marginRight: 6 };
const pend = { marginTop: 8, paddingTop: 6, borderTop: "1px dashed " + mix(22), fontSize: 11 };
const grpHdr = { fontSize: 10, fontWeight: 700, opacity: 0.5, letterSpacing: 0.4, margin: "8px 0 1px" };
// Uchwyt zmiany wysokości: niewidoczny pas przy dolnej krawędzi (wchodzi w dolny
// padding karteczki); widać go tylko po najechaniu, kursor ↕ podpowiada chwyt.
const handle = { height: 8, margin: "2px 0 -10px", borderRadius: 4, cursor: "ns-resize", background: "transparent" };
const HANDLE_HOVER = mix(10);

const trunc = (s, n = 42) => (s.length <= n ? s : s.slice(0, n - 1) + "…");
// Z tracebacku/komunikatu zostaw ostatnią niepustą linię (sedno błędu).
const errLine = (err) => trunc(String(err).trim().split("\n").filter(Boolean).pop() || "?", 60);

const TIER_LABELS = ["⏰ Po SLA", "⌛ Termin <48h", "Pozostałe"];

function openRow(r) {
  return (
    <a style={row} href={r.url} title={r.subject} key={r.id}>
      <span style={idc}>#{r.id}</span>{r.from_pending ? "💬 " : ""}{r.flags.join("")} {trunc(r.subject)}
    </a>
  );
}

// Otwarte: w sekcjach pilności (gdy grouped) z nagłówkiem przy zmianie tier,
// albo płasko (tryb „ostatnio" sortuje po dacie, bez sekcji).
function renderOpen(rows, grouped) {
  if (!grouped) return rows.map(openRow);
  const out = [];
  let last = null;
  rows.forEach((r) => {
    if (r.tier !== last) {
      last = r.tier;
      out.push(<div style={grpHdr} key={"h" + r.tier}>{TIER_LABELS[r.tier] || "—"}</div>);
    }
    out.push(openRow(r));
  });
  return out;
}

// --- render -----------------------------------------------------------------
export const render = (state, dispatch) => {
  const { output, error, busy, collapsed, hidden, height, last, theme, picker } = state;
  const T = themeOf(theme);
  const paint = { background: T.bg, color: T.fg };

  // Ukryta: tylko pinezka. Klik (bez przeciągnięcia) przywraca; nadal przeciągalna.
  if (hidden) {
    return (
      <div style={{ ...pinStyle, ...paint }} ref={(el) => initDrag(el, () => setUI(dispatch, { hidden: false }))}>
        📌 __LABEL__
      </div>
    );
  }

  // Świeże dane, a gdy ich brak (np. offline) — ostatnia zapamiętana kopia.
  const fresh = error ? null : parseData(output);
  const failed = !!error || (output !== "" && !fresh); // "" = komenda jeszcze nie wróciła
  const errText = error || (failed ? output : null);
  const d = fresh || last;
  const stale = !fresh && !!d && failed;
  const c = d && d.counts;

  const controls = (
    <span style={ctlWrap}>
      <span style={{ ...ctl, fontSize: 13 }} data-nodrag="1" title={`Kolor: ${theme}`}
            onClick={() => dispatch({ type: "FD/SET", patch: { picker: !picker } })}>🎨</span>
      <span style={ctl} data-nodrag="1" title="Odśwież teraz"
            onClick={() => refreshNow(dispatch)}>{busy ? "⏳" : "⟳"}</span>
      <span style={ctl} data-nodrag="1" title={collapsed ? "Rozwiń" : "Zwiń"}
            onClick={() => setUI(dispatch, { collapsed: !collapsed })}>{collapsed ? "▸" : "▾"}</span>
      <span style={ctl} data-nodrag="1" title="Ukryj (zostanie pinezka)"
            onClick={() => setUI(dispatch, { hidden: true })}>✕</span>
    </span>
  );

  const countsLine = c
    ? <span>
        {stale ? "📴 " : ""}🔴 {c.open} open ({c.open_sla} po SLA){c.pending > 0 ? ` · 🟡 ${c.pending} pending` : ""}
      </span>
    : <span>{errText ? "⚠️ błąd" : "—"}</span>;

  // Zwinięta: tylko pasek nagłówka (tytuł + liczniki + przyciski).
  if (collapsed) {
    return (
      <div style={{ ...rootStyle, ...paint, padding: "8px 14px" }} ref={(el) => initDrag(el, null)}>
        {picker && themePicker(theme, (name) => setUI(dispatch, { theme: name, picker: false }))}
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
    <div style={{ ...rootStyle, ...paint }} ref={(el) => initDrag(el, null)}>
        {picker && themePicker(theme, (name) => setUI(dispatch, { theme: name, picker: false }))}
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
        {stale && (
          <div style={{ ...sub, marginBottom: 4 }} title={String(errText)}>
            📴 brak połączenia — dane z {d.generated_at ? d.generated_at.slice(0, 16).replace("T", " ") : "?"}
          </div>
        )}
        {!d && errText && <div style={sub} title={String(errText)}>⚠️ błąd: {errLine(errText)}</div>}
        {!d && !errText && (
          <div style={sub}>Brak danych — sprawdź klucz API (~/.config/freshdesk/key).</div>
        )}
        {d && d.open && d.open.length === 0 && (
          <div style={sub}>brak otwartych 🎉</div>
        )}
        {d && d.open && renderOpen(d.open, d.grouped)}
        {d && d.pending && d.pending.filter((r) => r.bucket !== "fresh").length > 0 && (
          <div style={pend}>
            {d.pending.filter((r) => r.bucket !== "fresh").map((r) => (
              <a style={row} href={r.url} title={r.subject} key={r.id}>
                <span style={idc}>{r.bucket === "close" ? "🗑" : "🔔"} #{r.id}</span>{trunc(r.subject, 30)}{" "}
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
           onMouseEnter={(e) => { e.currentTarget.style.background = HANDLE_HOVER; }}
           onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
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
    """Złóż komendę fd_list dla widgetu z opcji generatora.

    Filtr włączający i wykluczający można łączyć: np. --query "CRM|ERP"
    z --exclude "SHOP" daje „(crm lub erp) i nie shop". Karteczka „pozostałe"
    (sam --exclude, bez --query) nie dostaje filtra włączającego — z label NIE
    robimy wtedy zapytania.
    """
    fd_args: list[str] = []
    if a.recent:
        fd_args.append("--recent")
    else:
        if a.query is not None:
            query = a.query
        elif a.exclude:
            query = None  # karteczka „pozostałe" — działa sam filtr wykluczający
        else:
            query = a.label
        if query:
            fd_args.append(f'"{query}"')
        if a.exclude:
            fd_args.append("--exclude")
            fd_args += [f'"{e}"' for e in a.exclude]
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
        .replace("__THEME__", a.theme)
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Generator karteczek Übersicht dla Freshdeska.")
    ap.add_argument("label", help="nazwa karteczki: tytuł + nazwa pliku + klucz pozycji")
    ap.add_argument("--query", default=None, help="filtr fd_list (domyślnie = label), np. 'ERP-CRM'")
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
    ap.add_argument(
        "--theme",
        default="grafit",
        help="kolor startowy: grafit, biały… albo '<barwa> <ton>', np. 'zielony ciemny' (potem 🎨)",
    )
    a = ap.parse_args()

    content = build_widget(a)
    out = Path(__file__).parent / "widgets" / f"freshdesk-{slug(a.label)}.jsx"
    out.write_text(content, encoding="utf-8")
    print(f"zapisano {out}")


if __name__ == "__main__":
    main()
