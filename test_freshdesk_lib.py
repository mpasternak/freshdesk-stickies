"""Testy czystej logiki (scoring, buckety, filtr) — bez sieci."""

from datetime import datetime, timedelta, timezone

import freshdesk_lib as fd

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def test_tokens_splits_on_separators():
    assert fd._tokens("APOZ-ATOM") == ["apoz", "atom"]
    assert fd._tokens("BPP") == ["bpp"]
    assert fd._tokens(None) == []
    assert fd._tokens("") == []


def test_or_groups_splits_alternatives_and_ands_within():
    # '|' rozdziela grupy (OR), spacja/myślnik łączy tokeny w grupie (AND)
    assert fd._or_groups("ATOM|APOZ") == [["atom"], ["apoz"]]
    assert fd._or_groups("BILLING ACME") == [["billing", "acme"]]
    assert fd._or_groups("BPP") == [["bpp"]]
    assert fd._or_groups(None) == []
    assert fd._or_groups("") == []


def test_or_include_matches_any_group():
    contacts = {"7": {"name": "Jan", "email": "jan@apoz.edu.pl"}}
    # zgłoszenie tylko z 'apoz' (w mailu), bez 'atom' w temacie
    apoz_only = {"subject": "Zmiana hasła", "requester_id": 7, "custom_fields": {}}
    groups = fd._or_groups("ATOM|APOZ")
    # OR: pasuje do grupy [apoz], mimo że nie ma 'atom'
    assert any(fd._matches(apoz_only, g, contacts) for g in groups)
    # a stary AND (jedna grupa atom+apoz) by tego NIE złapał
    assert not fd._matches(apoz_only, ["atom", "apoz"], contacts)


def test_matches_requires_all_tokens_across_haystack():
    contacts = {"7": {"name": "Jan", "email": "jan@acme.example.com"}}
    ticket = {"subject": "[ATOM] symulacja", "requester_id": 7, "custom_fields": {}}
    # ATOM w temacie + ACME w mailu zgłaszającego → trafia
    assert fd._matches(ticket, ["atom", "acme"], contacts)
    # token nieobecny → nie trafia
    assert not fd._matches(ticket, ["atom", "globex"], contacts)
    # brak tokenów → wszystko przechodzi
    assert fd._matches(ticket, [], contacts)


def test_score_breached_beats_fresh():
    breached = {
        "fr_due_by": _iso(NOW - timedelta(days=5)),
        "due_by": _iso(NOW - timedelta(days=3)),
        "created_at": _iso(NOW - timedelta(days=20)),
        "priority": 1,
        "responder_id": None,
    }
    fresh = {
        "fr_due_by": _iso(NOW + timedelta(days=5)),
        "due_by": _iso(NOW + timedelta(days=6)),
        "created_at": _iso(NOW - timedelta(hours=2)),
        "priority": 1,
        "responder_id": None,
    }
    s_breached, flags = fd.score_open(breached, NOW)
    s_fresh, _ = fd.score_open(fresh, NOW)
    assert s_breached > s_fresh
    assert "⏰SLA" in flags


def test_score_urgent_flag_and_weight():
    base = {
        "fr_due_by": _iso(NOW + timedelta(days=10)),
        "due_by": _iso(NOW + timedelta(days=10)),
        "created_at": _iso(NOW),
        "responder_id": None,
    }
    low, _ = fd.score_open({**base, "priority": 1}, NOW)
    urgent, flags = fd.score_open({**base, "priority": 4}, NOW)
    assert urgent == low + fd.W_PRIORITY[4]
    assert "🔴Urgent" in flags


def test_age_is_capped():
    ancient = {
        "fr_due_by": _iso(NOW + timedelta(days=10)),
        "due_by": _iso(NOW + timedelta(days=10)),
        "created_at": _iso(NOW - timedelta(days=999)),
        "priority": 1,
        "responder_id": None,
    }
    score, flags = fd.score_open(ancient, NOW)
    assert score == fd.W_AGE_CAP  # tylko wiek, dobity do limitu
    assert "🕸" in flags


def test_urgency_tier():
    assert fd.urgency_tier(["⏰SLA", "🔴Urgent"]) == 0  # po SLA bije wszystko
    assert fd.urgency_tier(["⌛<24h", "🟠High"]) == 1  # nadchodzący termin
    assert fd.urgency_tier(["⌛<48h"]) == 1
    assert fd.urgency_tier(["🟡Medium", "🕸"]) == 2  # tylko priorytet/wiek
    assert fd.urgency_tier([]) == 2


def test_last_reply_is_customer():
    a = _iso(NOW - timedelta(days=3))  # ja odpisałem 3 dni temu
    r = _iso(NOW - timedelta(days=1))  # klient odpisał 1 dzień temu (nowszy)
    # klient odpisał po mnie → piłka u mnie
    assert fd.last_reply_is_customer({"agent_responded_at": a, "requester_responded_at": r})
    # ja odpisałem po kliencie → piłka u klienta
    assert not fd.last_reply_is_customer({"agent_responded_at": r, "requester_responded_at": a})
    # klient nigdy nie odpisał → piłka u klienta
    assert not fd.last_reply_is_customer({"agent_responded_at": a, "requester_responded_at": None})
    # tylko klient odpisał (brak odpowiedzi agenta) → piłka u mnie
    assert fd.last_reply_is_customer({"agent_responded_at": None, "requester_responded_at": r})
    # brak jakichkolwiek danych → piłka u klienta (czekam na niego)
    assert not fd.last_reply_is_customer({})


def test_client_silence_days_from_pending_since():
    stats = {"pending_since": _iso(NOW - timedelta(days=21)), "agent_responded_at": _iso(NOW)}
    # liczone od pending_since, nie od agent_responded_at
    assert round(fd.client_silence_days(stats, {}, NOW)) == 21


def test_client_silence_days_fallbacks():
    # brak pending_since → agent_responded_at
    s1 = {"agent_responded_at": _iso(NOW - timedelta(days=5))}
    assert round(fd.client_silence_days(s1, {}, NOW)) == 5
    # brak stats → updated_at zgłoszenia
    t = {"updated_at": _iso(NOW - timedelta(days=9))}
    assert round(fd.client_silence_days({}, t, NOW)) == 9


def test_pending_bucket_thresholds():
    # świeże: cisza ≤ 7 dni → nic nie wymaga akcji
    assert fd.pending_bucket(0) == "fresh"
    assert fd.pending_bucket(fd.REMIND_DAYS) == "fresh"  # dokładnie na progu = jeszcze świeże
    # > 7 dni → 🔔 przypominajka
    assert fd.pending_bucket(fd.REMIND_DAYS + 0.1) == "remind"
    assert fd.pending_bucket(fd.CLOSE_DAYS) == "remind"  # dokładnie na progu zamknięcia = wciąż 🔔
    # > 14 dni → 🗑 kandydat do zamknięcia
    assert fd.pending_bucket(fd.CLOSE_DAYS + 0.1) == "close"
    assert fd.pending_bucket(99) == "close"
