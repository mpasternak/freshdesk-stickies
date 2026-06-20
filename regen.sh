#!/usr/bin/env bash
# Przegenerowuje WSZYSTKIE karteczki z aktualnego szablonu make_widget.py.
#
# --top/--left to tylko pozycje STARTOWE: po pierwszym przeciągnięciu myszą
# zapamiętana pozycja (localStorage, klucz fdpos-<slug>) ma pierwszeństwo, więc
# regeneracja nie przesuwa już raz ustawionych karteczek.
#
# Po regeneracji wgraj zmiany do Übersicht: ./install-widgets.sh
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

"$PY" make_widget.py "BPP"       --top 40  --left 40
"$PY" make_widget.py "ATOM-APOZ" --query "ATOM|APOZ" --exclude "BPP" --top 40 --left 430 --accent "#e07a3f"
"$PY" make_widget.py "APOZ"      --top 40  --left 820
"$PY" make_widget.py "Pozostałe" --top 360 --left 40  --accent "#777" --exclude "BPP" "ATOM-APOZ"
"$PY" make_widget.py "Ostatnio"  --top 360 --left 430 --recent --accent "#2e9e5b"
"$PY" make_widget.py "WSB"       --top 360 --left 820

echo "Przegenerowano wszystkie karteczki. Wgraj do Übersicht: ./install-widgets.sh"
