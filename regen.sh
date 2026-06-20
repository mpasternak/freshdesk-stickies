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

# Zbiór „BPP" zdefiniowany RAZ — to samo trafia do karteczki BPP (filtr włączający)
# i do wykluczenia w „Pozostałe". '|' = alternatywa (OR), spacja = AND w grupie.
# Domeny dopasowujemy w całości (kropka zostaje w tokenie). up.edu.pl ≡ up.lublin.pl
# (ta sama uczelnia). 'umlub' łapie umlub.pl oraz umlub.edu.pl.
# 'PBN' to pojęcie z systemu BPP → zgłoszenia z PBN idą do BPP (dotyczy zwł.
# Bihałowicza z @apoz.edu.pl: bez tego jego PBN-y wpadałyby do ATOM-APOZ przez
# 'apoz' z maila). Jego zgłoszenia ATOM nie mają bpp/pbn → zostają w ATOM-APOZ.
#
# Bihałowicz pisze do DWÓCH systemów, a każdy jego mail z @apoz.edu.pl zawiera
# 'apoz' → same z siebie wpadałyby do ATOM-APOZ. Dlatego jego zgłoszenia ze
# słowami treściowymi bibliografii też kierujemy do BPP (zwł. 'optymaliza' i
# 'dyscyplin' — u niego to ewaluacja/punktacja, nie meteo z ATOM). Te słowa są
# ZAWĘŻONE do jego maila ('jbihalowicz' + słowo), żeby nie ruszać cudzych
# zgłoszeń. Jego ATOM (meteo/hysplit/symulacja/leaflet) nie ma tych słów →
# zostaje w ATOM-APOZ.
BIH=jbihalowicz
BIH_BPP="$BIH importer|$BIH dyscyplin|$BIH autor|$BIH rozdział|$BIH czasopism|$BIH punktacj|$BIH optymaliza"
BPP_FILTER="BPP|PBN|Anna Czapczyńska|Anna Starek|Anna Wołodko|umlub|up.edu.pl|up.lublin.pl|$BIH_BPP"

# Zbiór „ATOM" — system atmosferyczny. Oprócz 'atom'/'apoz' rozpoznajemy go po
# jednoznacznie pogodowych słowach (AROME/GRIB/HYSPLIT to modele/formaty, meteo,
# symulacja). 'symulac' = rdzeń (łapie symulacja/symulacji). Definiujemy RAZ:
# karta ATOM-APOZ (włącz) i wykluczenie w „Pozostałe". Konflikt z BPP rozstrzyga
# wykluczenie BPP_FILTER w ATOM-APOZ → przy obu sygnałach wygrywa BPP.
ATOM_FILTER="ATOM|APOZ|meteo|arome|grib|hysplit|symulac"

"$PY" make_widget.py "BPP"       --query "$BPP_FILTER" --top 40 --left 40
"$PY" make_widget.py "ATOM-APOZ" --query "$ATOM_FILTER" --exclude "$BPP_FILTER" --top 40 --left 430 --accent "#e07a3f"
"$PY" make_widget.py "APOZ"      --top 40  --left 820
"$PY" make_widget.py "Pozostałe" --top 360 --left 40  --accent "#777" --exclude "$BPP_FILTER" "$ATOM_FILTER"
"$PY" make_widget.py "Ostatnio"  --top 360 --left 430 --recent --accent "#2e9e5b"
"$PY" make_widget.py "WSB"       --top 360 --left 820

echo "Przegenerowano wszystkie karteczki. Wgraj do Übersicht: ./install-widgets.sh"
