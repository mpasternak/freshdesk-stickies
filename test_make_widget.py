"""Testy składania komendy fd_list w generatorze widgetów."""

from argparse import Namespace

import make_widget as mw


def _ns(**kw):
    base = dict(
        label="BPP",
        query=None,
        exclude=None,
        recent=False,
        limit=None,
        top=40,
        left=40,
        accent="#3f7ae0",
    )
    base.update(kw)
    return Namespace(**base)


def test_default_query_is_label():
    cmd = mw.build_command(_ns(label="BPP"))
    assert cmd.endswith('fd_list.py "BPP" --json')


def test_query_overrides_label():
    cmd = mw.build_command(_ns(label="Lublin", query="up.lublin"))
    assert '"up.lublin"' in cmd
    assert '"Lublin"' not in cmd


def test_exclude_builds_pozostale():
    cmd = mw.build_command(_ns(label="Pozostałe", exclude=["BPP", "ATOM-APOZ"]))
    assert '--exclude "BPP" "ATOM-APOZ"' in cmd
    assert cmd.endswith("--json")


def test_recent_flag():
    cmd = mw.build_command(_ns(label="Ostatnio", recent=True))
    assert "--recent" in cmd
    assert '"Ostatnio"' not in cmd  # recent ignoruje filtr-nazwę


def test_limit_passthrough():
    cmd = mw.build_command(_ns(recent=True, limit=12))
    assert "--limit 12" in cmd


# --- generowanie całego pliku .jsx -----------------------------------------


def test_build_widget_substitutes_all_placeholders():
    src = mw.build_widget(_ns(label="BPP", accent="#abc123", top=11, left=22))
    for ph in ("__LABEL__", "__SLUG__", "__COMMAND__", "__TOP__", "__LEFT__", "__ACCENT__"):
        assert ph not in src, f"nie podstawiono {ph}"
    assert "Karteczka Freshdesk: BPP" in src  # nazwa trafia do nagłówka/komentarza
    assert "4px solid #abc123" in src  # akcent
    assert "{ x: 22, y: 11 }" in src  # pozycja startowa (left=x, top=y)


def test_build_widget_uses_interactive_ubersicht_api():
    src = mw.build_widget(_ns(label="BPP"))
    assert 'import { run } from "uebersicht"' in src
    assert "export const initialState" in src
    assert "export const updateState" in src


def test_build_widget_has_persistent_ui_and_position_keys():
    src = mw.build_widget(_ns(label="ATOM-APOZ"))
    assert '"fdpos-atom-apoz"' in src  # pozycja (jak dotychczas)
    assert '"fdui-atom-apoz"' in src  # zwinięcie / ukrycie / wysokość


def test_build_widget_has_collapse_hide_refresh_resize():
    src = mw.build_widget(_ns(label="BPP"))
    assert "refreshNow" in src and "Odśwież" in src  # przycisk odświeżania
    assert "collapsed" in src  # zwijanie do nagłówka
    assert "hidden" in src and "📌" in src  # ukrycie -> pinezka
    assert "ns-resize" in src and "startResize" in src  # zmiana wysokości od dołu
