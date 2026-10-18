#!/usr/bin/env bash
# Przegenerowuje WSZYSTKIE karteczki z aktualnego szablonu make_widget.py.
#
# Lista karteczek (nazwy, filtry, pozycje) jest PRYWATNA — filtry zwykle zawierają
# nazwiska i domeny klientów — więc nie leży w repo, tylko w
# ~/.config/freshdesk/notes.sh (albo pliku wskazanym przez FRESHDESK_NOTES).
# Wzór: notes.example.sh. W pliku wołasz `note "Nazwa" [opcje make_widget.py]`.
#
# --top/--left to tylko pozycje STARTOWE: po pierwszym przeciągnięciu myszą
# zapamiętana pozycja (localStorage, klucz fdpos-<slug>) ma pierwszeństwo, więc
# regeneracja nie przesuwa już raz ustawionych karteczek.
#
# Po regeneracji wgraj zmiany do Übersicht: ./install-widgets.sh
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
NOTES="${FRESHDESK_NOTES:-$HOME/.config/freshdesk/notes.sh}"

if [ ! -f "$NOTES" ]; then
  echo "Brak listy karteczek: $NOTES"
  echo "Skopiuj wzór:  cp notes.example.sh \"$NOTES\"  i dopasuj filtry."
  exit 1
fi

note() { "$PY" make_widget.py "$@"; }

# shellcheck source=notes.example.sh
source "$NOTES"

echo "Przegenerowano wszystkie karteczki. Wgraj do Übersicht: ./install-widgets.sh"
