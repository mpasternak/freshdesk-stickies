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


def test_pending_buckets():
    def t(days):
        return {"updated_at": _iso(NOW - timedelta(days=days))}

    assert fd.pending_bucket(t(2), NOW) == "fresh"
    assert fd.pending_bucket(t(7), NOW) == "remind"
    assert fd.pending_bucket(t(20), NOW) == "close"
