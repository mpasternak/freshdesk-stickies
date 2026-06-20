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

REMIND_DAYS = 5  # pending bez ruchu > tylu dni → 🔔 przypominajka
CLOSE_DAYS = 10  # pending bez ruchu > tylu dni → 🗑 kandydat do zamknięcia

OLD_DAYS = 14  # od kiedy doklejamy flagę 🕸 "stare"

_CACHE_DIR = Path.home() / ".cache" / "freshdesk"
_CONTACT_CACHE = _CACHE_DIR / "contacts.json"


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


def pending_bucket(t: dict, now: datetime) -> str:
    """Klasyfikacja pending po wieku od ostatniego ruchu (updated_at)."""
    age = _age_days(t.get("updated_at"), now)
    if age > CLOSE_DAYS:
        return "close"  # 🗑 kandydat do zamknięcia
    if age > REMIND_DAYS:
        return "remind"  # 🔔 przypominajka należna
    return "fresh"  # czeka, świeże


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
    if recent:
        open_items.sort(key=lambda r: r["created_at"], reverse=True)
    else:
        open_items.sort(key=lambda r: (-r["score"], r["created_at"]))
    if limit:
        open_items = open_items[:limit]

    pending_items = []
    for t in raw_pending:
        if not keep(t):
            continue
        bucket = pending_bucket(t, now)
        pending_items.append(_row(t, contacts, now, bucket=bucket))
    # najpierw do zamknięcia, potem do przypomnienia, potem świeże; w grupie starsze wyżej
    order = {"close": 0, "remind": 1, "fresh": 2}
    pending_items.sort(key=lambda r: (order[r["bucket"]], r["updated_at"]))

    return {
        "project": project or ("pozostałe" if exclude_lists else "wszystko"),
        "generated_at": now.isoformat(timespec="seconds"),
        "open": open_items,
        "pending": pending_items,
        "counts": {
            "open": len(open_items),
            "open_sla": sum(1 for r in open_items if "⏰SLA" in r["flags"]),
            "pending": len(pending_items),
            "remind": sum(1 for r in pending_items if r["bucket"] == "remind"),
            "close": sum(1 for r in pending_items if r["bucket"] == "close"),
        },
    }


def _row(t, contacts, now, *, score=0, flags=None, bucket=None) -> dict:
    c = contacts.get(str(t.get("requester_id")), {})
    ts = t.get("updated_at") if bucket else t.get("created_at")
    return {
        "id": t["id"],
        "url": panel_url(t["id"]),
        "subject": (t.get("subject") or "").strip() or "(bez tematu)",
        "priority": t.get("priority", 1),
        "score": score,
        "flags": flags or [],
        "bucket": bucket,
        "requester": c.get("name") or c.get("email") or "",
        "age_days": round(_age_days(ts, now), 1),
        "created_at": t.get("created_at") or "",
        "updated_at": t.get("updated_at") or "",
    }
