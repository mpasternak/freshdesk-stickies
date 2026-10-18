# Wzór listy karteczek dla regen.sh. Skopiuj do ~/.config/freshdesk/notes.sh
# i dopasuj — tamten plik jest prywatny (filtry zawierają nazwiska / domeny
# klientów), więc nie trafia do repo.
#
# note "Nazwa" [--query FILTR] [--exclude FILTR...] [--recent] [--top Y --left X] [--accent KOLOR]
#
# Filtr: '|' = alternatywa (OR), spacja = AND w grupie. Domeny dopasowujemy
# w całości (kropka zostaje w tokenie).

# Zbiór „Webapp" zdefiniowany RAZ — trafia do karteczki Webapp (filtr włączający)
# i do wykluczenia w „Pozostałe". Łapie temat, domenę klienta i osobę kontaktową.
WEBAPP_FILTER="Webapp|acme.example.com|Jan Testowy"
BILLING_FILTER="BILLING ACME"

note "Webapp"       --query "$WEBAPP_FILTER" --top 40 --left 40
note "BILLING-ACME" --query "$BILLING_FILTER" --top 40 --left 430 --accent "#e07a3f"
note "Pozostałe"    --top 360 --left 40  --accent "#777" --exclude "$WEBAPP_FILTER" "$BILLING_FILTER"
note "Ostatnio"     --top 360 --left 430 --recent --accent "#2e9e5b"
