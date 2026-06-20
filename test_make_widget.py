"""Testy składania komendy fd_list w generatorze widgetów."""

from argparse import Namespace

import make_widget as mw


def _ns(**kw):
    base = dict(label="BPP", query=None, exclude=None, recent=False, limit=None)
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
