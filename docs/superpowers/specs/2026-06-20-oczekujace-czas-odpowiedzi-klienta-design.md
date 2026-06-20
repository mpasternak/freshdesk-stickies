# Oczekujące: czas odpowiedzi klienta + porządek z zegarkiem/SLA

Data: 2026-06-20
Status: do recenzji

## 1. Cel

Zgłoszenia „oczekujące" (Freshdesk `status:3`) mają dziś prymitywną obsługę:
kubełki po `updated_at` (🔔 >5 dni, 🗑 >10 dni), bez rozróżnienia **kto
odpowiedział ostatni**. To miesza dwie zupełnie różne sytuacje:

- **piłka jest u mnie** — klient odpisał i czeka na moją reakcję,
- **piłka jest u klienta** — ja odpisałem i to klient zwleka.

Cel: oczekujące mają odzwierciedlać, **co realnie wymaga mojej akcji**, oraz
osobno sygnalizować, że to *klient* się ślimaczy z odpowiedzią.

## 2. Reguła docelowa (sedno)

Dla każdego zgłoszenia o statusie `pending` decyduje **kto wysłał ostatnią
wiadomość** oraz **jak długo klient milczy**:

| Stan oczekującego | Widoczne? | Jak wyświetlone |
|---|---|---|
| **Klient odpisał ostatni** (piłka u mnie) | ✅ TAK | w liście „otwarte", pełny scoring + SLA + zegarek jak otwarte |
| **Ja odpisałem ostatni, klient milczy ≤ 14 dni** | ❌ NIE | ukryte — nic nie wymaga akcji |
| **Ja odpisałem ostatni, klient milczy > 14 dni** | ✅ TAK | w sekcji oczekujących, z etykietą `🐌 klient Nd` |

- „14 dni" liczone od `pending_since` (= moment, w którym piłka przeszła do
  klienta / moja ostatnia odpowiedź), **nie** od daty zgłoszenia.
- Stare kubełki 🔔 (5 dni) / 🗑 (10 dni) oraz `pending_bucket()` **znikają**
  całkowicie — zastępuje je powyższa logika.
- Etykieta spóźnionej odpowiedzi klienta: `🐌 klient Nd`, gdzie `N` = liczba
  dni ciszy klienta (np. `🐌 klient 21d`).

## 3. Źródło danych: kto odpowiedział ostatni

Wynik `/search/tickets` **nie** zawiera tej informacji. Daje ją natomiast
obiekt `stats` (parametr `include=stats`) — zweryfikowane na żywo na realnym
API:

```
agent_responded_at, requester_responded_at, pending_since,
status_updated_at, first_responded_at, ...
```

Klasyfikacja:

- **klient odpisał ostatni** ⟺ `requester_responded_at` istnieje **i**
  (`agent_responded_at` nie istnieje **lub** `requester_responded_at >
  agent_responded_at`).
- w przeciwnym razie → **ja odpisałem ostatni** (lub nikt) → piłka u klienta,
  cisza = `now − pending_since` (fallback: `agent_responded_at`, dalej
  `updated_at`).

`stats` nie ma w wyszukiwarce, więc pobieramy je **per zgłoszenie po ID**
(`GET /tickets/{id}?include=stats`). Dotyczy to **tylko oczekujących**
(`status:3`) — u użytkownika ~10 sztuk. Otwarte (`status:2`) zostają bez
zmian, czytane hurtem z wyszukiwarki.

### Efekt uboczny: oczekujące „na żywo" (naprawia „⟳")

Zapytanie po ID zwraca **bieżący** stan zgłoszenia (wyszukiwarka Freshdeska
to asynchroniczny indeks z opóźnieniem ~1–2 min). Skoro i tak dociągamy każdy
oczekujący po ID, **używamy `status` z tej żywej odpowiedzi**:

- live `status` ∈ {2 open, 3 pending} → klasyfikujemy jak wyżej,
- live `status` ∈ {4 resolved, 5 closed, spam, deleted} → **pomijamy**
  (właśnie zamknięte zgłoszenie znika od razu po „⟳", bez czekania na indeks).

Dla **otwartych** krótkie opóźnienie indeksu zostaje (live-weryfikacja ~83
otwartych = ryzyko HTTP 429); samo się zgrywa po chwili. Świadoma decyzja —
patrz §8.

### Cache `stats`

Plik `~/.cache/freshdesk/stats.json`:

```json
{ "379": { "updated_at": "2026-06-19T19:15:47Z", "stats": { ... }, "status": 3 } }
```

Klucz świeżości = `updated_at`. Jeśli `updated_at` z wyszukiwarki == zapisany
→ używamy cache (zero zapytań). Jeśli różny lub brak → pobieramy po ID i
nadpisujemy. W stanie ustalonym (nic się nie zmienia) odświeżenie nie generuje
dodatkowych zapytań.

## 4. Zmiany w `freshdesk_lib.py`

**Stałe:**
- usuń `REMIND_DAYS`, `CLOSE_DAYS`,
- dodaj `CLIENT_SILENCE_DAYS = 14` (próg ciszy klienta; osobny byt od
  `OLD_DAYS = 14`, które dalej znaczy „wiek otwartego → 🕸").

**Usuń** `pending_bucket()`.

**Dodaj** czyste funkcje (testowalne bez sieci):

```python
def last_reply_is_customer(stats: dict) -> bool: ...
def client_silence_days(stats: dict, t: dict, now) -> float: ...
```

**Dodaj** pobranie z cache:

```python
def _ticket_with_stats(ticket_id: int, updated_at: str) -> dict | None:
    # cache po (id, updated_at); zwraca pełny tykiet z 'stats' i live 'status'
    # błąd HTTP → log na stderr + None (NIE cichego połykania — patrz §7)
```

**`build()`** — nowy przepływ dla `raw_pending`:

```python
for t in raw_pending:
    if not keep(t):
        continue
    full = _ticket_with_stats(t["id"], t.get("updated_at") or "")
    if full is None:                       # błąd pobrania stats
        # fallback bezpieczny: traktuj jak ciszę klienta wg updated_at
        full, st = t, t.get("status")
    st = full.get("status", t.get("status"))
    if st not in (2, 3):                    # live: już zamknięte/spam → pomiń
        continue
    stats = full.get("stats") or {}
    if last_reply_is_customer(stats):       # piłka u mnie → jak otwarte
        score, flags = score_open(full, now)
        open_items.append(_row(full, contacts, now, score=score,
                               flags=flags, from_pending=True))
    else:                                   # piłka u klienta
        silence = client_silence_days(stats, full, now)
        if silence > CLIENT_SILENCE_DAYS:   # >14 dni → 🐌, inaczej ukryte
            pending_items.append(_row(full, contacts, now,
                                      silence_days=round(silence, 1)))
```

- `open_items` sortowane jak dotąd (`-score, created_at`); doklejone
  „klient-odpisał" wchodzą w to naturalnie (mają `score`/`flags`).
- `recent`/`limit`/`exclude` działają bez zmian (filtr `keep` ten sam; w trybie
  `recent` doklejone też sortują się po dacie).
- `pending_items` sortowane malejąco po `silence_days` (najdłużej milczący na
  górze).

**`_row()`** — rozszerz sygnaturę o `from_pending=False` i `silence_days=None`;
dodaj te pola do zwracanego słownika. Usuń `bucket`.

Schemat wiersza:
- **otwarte** (w tym doklejone): `{id, url, subject, priority, score, flags,
  requester, age_days, created_at, updated_at, from_pending}`.
- **oczekujące** (tylko cisza >14 dni): jw. + `silence_days`, `flags=[]`,
  `score=0`, `from_pending=False`.

**`build()` → `counts`:** usuń `remind`/`close`. Zostaje:
- `open` = `len(open_items)` (z doklejonymi),
- `open_sla` = liczba z `⏰SLA`,
- `pending` = `len(pending_items)` (tylko 🐌 „klient milczy >14 dni").

## 5. Render — `fd_list.py` (`_text`)

- Druga linia nagłówka: usuń `(N przypomnij, M zamknij)`. Np.
  `🔴 K open (S po SLA) · 🐌 P klient milczy`.
- Sekcja oczekujących: zamiast `{close/remind/fresh}` jedna ikona 🐌, wiersz
  `🐌 #id <temat> · klient Nd`.
- (opcjonalnie) doklejone „klient odpisał" mogą mieć subtelny znacznik (💬) —
  patrz §9.

## 6. Render — `make_widget.py` (szablon JSX)

- **`countsLine`**: `🔴 {open} open ({open_sla} po SLA) · 🐌 {pending} klient`.
- **Wiersze otwartych**: bez zmian (`r.flags.join("")` — doklejone mają flagi
  ze `score_open`). Jeśli przyjmiemy znacznik 💬 dla `from_pending` — mały
  prefiks przed tematem.
- **Sekcja oczekujących**: zastąp obecny blok `d.pending.filter(bucket !==
  "fresh")`. Nowy: renderuj `d.pending` (już tylko >14 dni) jako wiersze
  `<span idc>🐌 #{id}</span>{temat}` z dopiskiem „klient {silence_days|0}d"
  (wyciszony). Brak `d.pending` → sekcja znika.
- `pend` styl, uchwyt resize, drag, zwijanie, chowanie — bez zmian.

## 7. Obsługa błędów (zgodnie z regułą projektu)

- `_ticket_with_stats` przy `HTTPError`/timeout: **log na stderr** (`print(...,
  file=sys.stderr)` — JSON leci na stdout, więc stderr jest bezpieczny) i
  zwraca `None`. `build()` robi wtedy bezpieczny fallback (traktuje jak ciszę
  klienta wg `updated_at`), zamiast wywalać cały widget. Żadnego cichego
  `except: pass`.
- Parsowanie `stats` z brakującymi polami → `_parse_dt(None)` zwraca `None`,
  logika klasyfikacji to przewiduje.

## 8. „⟳ nie odświeża" — decyzja

Przyczyna potwierdzona: opóźnienie indeksu wyszukiwarki Freshdeska (`/search`),
nie nasz cache (każdy `_get` to świeży request; potwierdza to HTTP 429 przy
nasilonym odpytywaniu). Decyzja:

- **oczekujące** stają się „na żywo" za darmo (czytamy je po ID — §3),
- **otwarte** zostawiamy z krótkim opóźnieniem indeksu (live-weryfikacja
  wszystkich otwartych = ryzyko 429; opóźnienie samo mija po ~1–2 min),
- **odrzucone:** przejście otwartych na realtime `GET /tickets` (list API) —
  domyślne okno 30 dni ukryłoby stare otwarte (a właśnie one są ważne: 🕸).

## 9. Otwarte drobiazgi do potwierdzenia w recenzji

- **Znacznik doklejonych**: czy „klient odpisał" (doklejone do otwartych) ma
  mieć subtelny prefiks 💬 (żeby było wiadomo, że to wróciło od klienta), czy
  ma wyglądać 1:1 jak otwarte? Propozycja: lekki 💬, łatwy do usunięcia.
- **Etykieta**: zatwierdzone `🐌 klient Nd`.

## 10. Testy

- **Usuń** `test_pending_buckets`.
- **Dodaj** (czyste, bez sieci):
  - `test_last_reply_is_customer` — klient nowszy / agent nowszy / requester
    `null` / agent `null` / oba `null`.
  - `test_client_silence_days` — liczone od `pending_since`; fallback gdy brak.
- `build()`/`_ticket_with_stats` (sieć/cache) zostają bez testów jednostkowych,
  zgodnie z dotychczasową konwencją (testujemy czystą logikę).
- `test_make_widget.py`: dostosować, jeśli zmiana `countsLine`/sekcji łamie
  asercje na treści szablonu.

## 11. Poza zakresem

- Zmiana sortowania otwartych, scoringu, dragowania, resize, chowania.
- Realtime dla otwartych (§8, odrzucone).
- Konfigurowalność progu 14 dni z CLI (stała w kodzie, jak reszta progów).
