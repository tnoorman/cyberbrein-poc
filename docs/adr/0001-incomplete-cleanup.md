# ADR-0001: Onvolledige cleanup na geverifieerde opslag

- Status: Voorgesteld
- Datum: 2026-08-06

## Context

Pipeline-exitcode 4 betekent dat PostgreSQL/PostGIS-opslag en de terugleescontrole zijn geslaagd,
maar dat een of meer tijdelijke invoerbestanden niet konden worden verwijderd. De launcher toont
nu hetzelfde hersteladvies als bij een mislukte verwerking en stelt `resume` voor. Opnieuw
verwerken is in deze toestand niet nodig en kan de betekenis van de al opgeslagen ronde
vertroebelen. Bovendien kan `discard` na een gedeeltelijke cleanup mislukken doordat het ontbreken
van één bestand als fout wordt behandeld.

## Besluit

- Exitcode 4 blijft onderdeel van het publieke runtimecontract.
- De launcher meldt expliciet dat Storage is geverifieerd en start het dashboard niet automatisch.
- `resume` wordt niet als herstelactie aangeboden; de resultaten zijn via `dashboard` beschikbaar.
- De operator controleert de resterende paden en gebruikt daarna expliciet `discard`.
- De normale Pipeline-cleanup blijft strikt. Alleen de expliciete discard-route mag reeds
  ontbrekende runtimebestanden tolereren.
- Exitcodes en cleanupfuncties worden als afzonderlijk Pipeline-runtimecontract aangeboden en niet
  uit de CLI-module geïmporteerd.

## Alternatieven

- Automatisch opnieuw verwerken is afgewezen omdat de opslag al is geverifieerd.
- Exitcode 4 als succes (`0`) behandelen is afgewezen omdat privacygevoelige tijdelijke invoer kan
  zijn achtergebleven.
- Alle cleanup altijd tolerant maken is afgewezen omdat dit fouten in het normale succespad kan
  verbergen.

## Gevolgen

De gebruiker krijgt toestandsspecifiek hersteladvies. `discard` moet veilig omgaan met een
gedeeltelijk verwijderde set, terwijl symlinks en niet-reguliere bestanden afgewezen blijven.
