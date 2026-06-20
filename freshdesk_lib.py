"""Rdzeń logiki sticky-notes z Freshdeska: pobranie, scoring, filtr per projekt.

Czysty stdlib (urllib) — żeby działało na każdym python3 na macOS bez pip.
Tej samej hierarchii scoringu używa skill `freshdesk` (SLA → termin → priorytet
→ wiek); tu jest jej wykonalna wersja.

Konfiguracja (nic wrażliwego nie jest zaszyte w kodzie):
- domena: zmienna FRESHDESK_DOMAIN albo plik ~/.config/freshdesk/domain
  (np. "twojakonto.freshdesk.com")
- klucz API: zmienna FRESHDESK_API_KEY albo plik ~/.config/freshdesk/key
  (Freshdesk → profil → "Your API Key")
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_CONFIG_DIR = Path.home() / ".config" / "freshdesk"

# Progi i wagi — odpowiadają opisowi w SKILL.md. Łatwe do strojenia w jednym
# miejscu (np. podbij URGENT, jeśli Urgent ma zawsze bić wiek).
W_FR_BREACH = 100  # SLA pierwszej odpowiedzi po terminie
W_DUE_BREACH = 80  # SLA rozwiązania po terminie
W_DUE_24H = 40  # dowolny termin w ciągu 24 h
W_DUE_48H = 20  # dowolny termin w ciągu 48 h
W_PRIORITY = {4: 30, 3: 20, 2: 10, 1: 0}  # Urgent/High/Medium/Low
W_AGE_PER_DAY = 1
W_AGE_CAP = 30

OLD_DAYS = 14  # wiek otwartego zgłoszenia → flaga 🕸 "stare"
CLIENT_SILENCE_DAYS = 14  # oczekujące: cisza klienta > tylu dni → 🐌 "klient Nd"

_CACHE_DIR = Path.home() / ".cache" / "freshdesk"
_CONTACT_CACHE = _CACHE_DIR / "contacts.json"
_STATS_CACHE = _CACHE_DIR / "stats.json"


# ── Konfiguracja / HTTP ──────────────────────────────────────────────────────


def _from_env_or_file(env: str, filename: str, human: str) -> str:
    val = os.environ.get(env)
    if val:
        return val.strip()
    path = _CONFIG_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    raise SystemExit(f"Brak: {human}. Ustaw {env} albo wpisz do {path}.")


def _api_key() -> str:
    return _from_env_or_file("FRESHDESK_API_KEY", "key", "klucz API (Freshdesk → profil → Your API Key)")


def _domain() -> str:
    return _from_env_or_file("FRESHDESK_DOMAIN", "domain", "domena (np. twojekonto.freshdesk.com)")


def panel_url(ticket_id: int) -> str:
    return f"https://{_domain()}/a/tickets/{ticket_id}"


def _get(path: str, params: dict | None = None) -> dict | list:
    url = f"https://{_domain()}/api/v2/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    token = base64.b64encode(f"{_api_key()}:X".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── Pobranie zgłoszeń ────────────────────────────────────────────────────────


def _search_all(status: int) -> list[dict]:
    """Wszystkie zgłoszenia o danym statusie — stronicowane (search: do 10 stron)."""
    out: list[dict] = []
    for page in range(1, 11):
        # query MUSI być w cudzysłowach — inaczej API zwraca "invalid".
        data = _get("search/tickets", {"query": f'"status:{status}"', "page": page})
        results = data.get("results", []) if isinstance(data, dict) else []
        out.extend(results)
        if len(results) < 30:  # ostatnia strona
            break
    return out


# ── Rozwijanie kontaktów (z cache na dysku) ──────────────────────────────────


def _load_contact_cache() -> dict:
    if _CONTACT_CACHE.exists():
        try:
            return json.loads(_CONTACT_CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_contact_cache(cache: dict) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _CONTACT_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def _resolve_contacts(ids: set[int]) -> dict:
    """id zgłaszającego → {name, email}. Dociąga tylko brakujące, resztę z cache."""
    cache = _load_contact_cache()
    dirty = False
    for cid in ids:
        if str(cid) in cache:
            continue
        try:
            c = _get(f"contacts/{cid}")
            cache[str(cid)] = {"name": c.get("name") or "", "email": c.get("email") or ""}
        except urllib.error.HTTPError:
            cache[str(cid)] = {"name": "", "email": ""}  # usunięty / agent
        dirty = True
    if dirty:
        _save_contact_cache(cache)
    return cache


# ── Pełny tykiet ze „stats" (cache na dysku po id+updated_at) ────────────────


def _load_stats_cache() -> dict:
    if _STATS_CACHE.exists():
        try:
            return json.loads(_STATS_CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_stats_cache(cache: dict) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _STATS_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def _ticket_with_stats(ticket_id: int, updated_at: str, cache: dict) -> dict | None:
    """Pełny tykiet z `stats` i ŻYWYM `status`. Cache po (id, updated_at).

    `updated_at` z wyszukiwarki to klucz świeżości — gdy się nie zmienił, cały
    tykiet (a więc i stats) jest ten sam. Błąd sieci/HTTP zwraca None (zalogowany
    na stderr); wołający robi bezpieczny fallback zamiast wywalać widget.
    """
    hit = cache.get(str(ticket_id))
    if hit and hit.get("updated_at") == updated_at:
        return hit.get("ticket")
    try:
        full = _get(f"tickets/{ticket_id}", {"include": "stats"})
    except OSError as e:  # urllib.error.URLError/HTTPError i timeouty to OSError
        print(f"freshdesk: nie pobrano stats #{ticket_id}: {e}", file=sys.stderr)
        return None
    cache[str(ticket_id)] = {"updated_at": updated_at, "ticket": full}
    return full


# ── Scoring ──────────────────────────────────────────────────────────────────


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _age_days(created: str | None, now: datetime) -> float:
    dt = _parse_dt(created)
    return (now - dt).total_seconds() / 86400 if dt else 0.0


def score_open(t: dict, now: datetime) -> tuple[int, list[str]]:
    """Zwraca (score, flagi). Wyżej = pilniejsze."""
    score = 0
    flags: list[str] = []

    fr = _parse_dt(t.get("fr_due_by"))
    due = _parse_dt(t.get("due_by"))

    # SLA przeterminowane. "brak odpowiedzi agenta" przybliżamy responder_id==null
    # (konto jednoosobowe) — pełną pewność daje dopiero konwersacja, której tu
    # świadomie nie dociągamy (widget ma być szybki).
    breached = False
    if fr and fr < now and not t.get("responder_id"):
        score += W_FR_BREACH
        breached = True
    if due and due < now:
        score += W_DUE_BREACH
        breached = True
    if breached:
        flags.append("⏰SLA")
    else:
        # nie przeterminowane → jak blisko najbliższy termin
        upcoming = [d for d in (fr, due) if d and d > now]
        if upcoming:
            hrs = min((d - now).total_seconds() / 3600 for d in upcoming)
            if hrs <= 24:
                score += W_DUE_24H
                flags.append("⌛<24h")
            elif hrs <= 48:
                score += W_DUE_48H
                flags.append("⌛<48h")

    pr = t.get("priority", 1)
    score += W_PRIORITY.get(pr, 0)
    if pr == 4:
        flags.append("🔴Urgent")
    elif pr == 3:
        flags.append("🟠High")
    elif pr == 2:
        flags.append("🟡Medium")

    age = _age_days(t.get("created_at"), now)
    score += min(int(age) * W_AGE_PER_DAY, W_AGE_CAP)
    if age >= OLD_DAYS:
        flags.append("🕸")

    return score, flags


def last_reply_is_customer(stats: dict) -> bool:
    """Czy OSTATNIA wiadomość w zgłoszeniu jest od klienta (piłka u mnie).

    Porównujemy znaczniki ze `stats` (include=stats). Brak odpowiedzi klienta
    (`requester_responded_at` puste) → piłka u klienta (czekam na niego).
    """
    a = _parse_dt(stats.get("agent_responded_at"))
    r = _parse_dt(stats.get("requester_responded_at"))
    if r is None:
        return False
    if a is None:
        return True
    return r > a


def client_silence_days(stats: dict, t: dict, now: datetime) -> float:
    """Ile dni klient milczy, odkąd piłka jest po jego stronie.

    Liczone od `pending_since` (moment przejścia w oczekiwanie / moja ostatnia
    odpowiedź). Fallbacky, gdyby `stats` było niepełne.
    """
    since = stats.get("pending_since") or stats.get("agent_responded_at") or t.get("updated_at")
    return _age_days(since, now)


# ── Filtr per projekt/osoba ──────────────────────────────────────────────────


def _haystack(t: dict, contacts: dict) -> str:
    c = contacts.get(str(t.get("requester_id")), {})
    parts = [
        t.get("subject") or "",
        (t.get("custom_fields") or {}).get("cf_adres_url") or "",
        c.get("name", ""),
        c.get("email", ""),
    ]
    return " ".join(parts).lower()


def _matches(t: dict, tokens: list[str], contacts: dict) -> bool:
    if not tokens:
        return True
    hay = _haystack(t, contacts)
    return all(tok in hay for tok in tokens)


def _tokens(project: str | None) -> list[str]:
    if not project:
        return []
    return [tok.lower() for tok in re.split(r"[^0-9a-zA-ZąćęłńóśżźĄĆĘŁŃÓŚŻŹ]+", project) if tok]


# ── Publiczne API ────────────────────────────────────────────────────────────


def build(
    project: str | None = None,
    exclude: list[str] | None = None,
    recent: bool = False,
    limit: int | None = None,
) -> dict:
    """Zbuduj listę zgłoszeń dla karteczki.

    - project: filtr włączający (tokeny AND po temacie+URL+zgłaszającym). None = wszystko.
    - exclude: lista filtrów wyłączających — zgłoszenie odpada, gdy pasuje do
      KTÓREGOKOLWIEK z nich. Tak robimy karteczkę „pozostałe" (NIE pasujące do
      żadnego z wymienionych projektów).
    - recent: zamiast scoringu sortuj otwarte malejąco po dacie zgłoszenia
      (najnowsze u góry) — karteczka „ostatnio zgłoszone".
    - limit: przytnij listę otwartych do N pozycji.
    """
    now = datetime.now(timezone.utc)
    tokens = _tokens(project)
    exclude_lists = [toks for toks in (_tokens(e) for e in (exclude or [])) if toks]

    raw_open = _search_all(2)
    raw_pending = _search_all(3)

    req_ids = {t["requester_id"] for t in raw_open + raw_pending if t.get("requester_id")}
    contacts = _resolve_contacts(req_ids)

    def keep(t: dict) -> bool:
        if not _matches(t, tokens, contacts):
            return False
        return not any(_matches(t, toks, contacts) for toks in exclude_lists)

    open_items = []
    for t in raw_open:
        if not keep(t):
            continue
        score, flags = score_open(t, now)
        open_items.append(_row(t, contacts, now, score=score, flags=flags))

    # Oczekujące: dla każdego dociągamy „stats" (kto odpisał ostatni) + żywy status.
    #  - klient odpisał ostatni (piłka u mnie)      → doklej do otwartych, scoring jak otwarte,
    #  - ja odpisałem, klient milczy ≤ 14 dni       → ukryte (nic nie wymaga akcji),
    #  - ja odpisałem, klient milczy > 14 dni       → sekcja oczekujących z 🐌.
    pending_items = []
    stats_cache = _load_stats_cache()
    stats_dirty = False
    for t in raw_pending:
        if not keep(t):
            continue
        upd = t.get("updated_at") or ""
        cached = stats_cache.get(str(t["id"]))
        full = _ticket_with_stats(t["id"], upd, stats_cache)
        if full is None:
            full = t  # błąd pobrania → bezpieczny fallback na dane z wyszukiwarki
        elif not (cached and cached.get("updated_at") == upd):
            stats_dirty = True  # realne pobranie po ID
        if full.get("status", t.get("status")) not in (2, 3):
            continue  # live: już zamknięte / spam / kosz → znika od razu (bez czekania na indeks)
        stats = full.get("stats") or {}
        if last_reply_is_customer(stats):
            score, flags = score_open(full, now)
            open_items.append(_row(full, contacts, now, score=score, flags=flags, from_pending=True))
        else:
            silence = client_silence_days(stats, full, now)
            if silence > CLIENT_SILENCE_DAYS:
                pending_items.append(_row(full, contacts, now, silence_days=round(silence, 1)))
    if stats_dirty:
        _save_stats_cache(stats_cache)

    if recent:
        open_items.sort(key=lambda r: r["created_at"], reverse=True)
    else:
        open_items.sort(key=lambda r: (-r["score"], r["created_at"]))
    if limit:
        open_items = open_items[:limit]

    # najdłużej milczący klient u góry
    pending_items.sort(key=lambda r: r["silence_days"], reverse=True)

    return {
        "project": project or ("pozostałe" if exclude_lists else "wszystko"),
        "generated_at": now.isoformat(timespec="seconds"),
        "open": open_items,
        "pending": pending_items,
        "counts": {
            "open": len(open_items),
            "open_sla": sum(1 for r in open_items if "⏰SLA" in r["flags"]),
            "pending": len(pending_items),
        },
    }


def _row(t, contacts, now, *, score=0, flags=None, from_pending=False, silence_days=None) -> dict:
    c = contacts.get(str(t.get("requester_id")), {})
    ts = t.get("updated_at") if silence_days is not None else t.get("created_at")
    return {
        "id": t["id"],
        "url": panel_url(t["id"]),
        "subject": (t.get("subject") or "").strip() or "(bez tematu)",
        "priority": t.get("priority", 1),
        "score": score,
        "flags": flags or [],
        "from_pending": from_pending,  # „klient odpisał" doklejone do otwartych
        "silence_days": silence_days,  # tylko oczekujące >14 dni (🐌 klient Nd)
        "requester": c.get("name") or c.get("email") or "",
        "age_days": round(_age_days(ts, now), 1),
        "created_at": t.get("created_at") or "",
        "updated_at": t.get("updated_at") or "",
    }
