#!/usr/bin/env bash
# Kopiuje wygenerowane widgety do katalogu widgetów Übersicht.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/widgets"
DEST="$HOME/Library/Application Support/Übersicht/widgets"

if [ ! -d "$DEST" ]; then
  echo "Nie znaleziono katalogu Übersicht: $DEST"
  echo "Zainstaluj i uruchom Übersicht (brew install --cask ubersicht), potem ponów."
  exit 1
fi

shopt -s nullglob
files=("$SRC"/freshdesk-*.jsx)
if [ ${#files[@]} -eq 0 ]; then
  echo "Brak widgetów w $SRC — najpierw: python3 make_widget.py \"NAZWA\""
  exit 1
fi

cp "${files[@]}" "$DEST"/
echo "Skopiowano ${#files[@]} widget(ów) do Übersicht. Odśwież: menu Übersicht → Refresh All Widgets (⌘R)."
