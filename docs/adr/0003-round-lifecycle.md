# ADR-0003: Persistente lifecycle en vastgezet verwerkingsbeleid

- Status: Geaccepteerd
- Datum: 2026-08-06

## Context

De toestand van een onderbroken meetronde wordt nu afgeleid uit aanwezige bestanden en de laatst
getoonde exitcode. `resume` leest zones en maximale GPS-nauwkeurigheid opnieuw uit flags of de
omgeving. Daardoor kan dezelfde bronbuffer onder een ander beleid worden verwerkt. Alleen het pad
naar een zonebestand bewaren lost dit niet op, omdat de inhoud op dat pad kan wijzigen.

## Besluit

- Een actieve ronde krijgt een klein mode-`0600` JSON-record met een expliciete toestand en een
  gevalideerde transitietabel.
- De gevalideerde GeoJSON-bytes worden voor de duur van de ronde gekopieerd naar een mode-`0600`
  snapshot. Het record bevat de SHA-256-digest van die snapshot en de gekozen maximale
  GPS-nauwkeurigheid.
- Nieuwe rondes hervatten uitsluitend met het vastgezette beleid. Conflicterende overrides worden
  afgewezen. Rondes van vóór deze wijziging zonder record en snapshot behouden het oude gedrag.
- Ontbrekende metadata is alleen legacy wanneer record én snapshot ontbreken. Een corrupt record,
  een losse snapshot of een digestverschil faalt gesloten.
- `PREPARED` en `COLLECTED` zijn hervatbaar. `UNUSABLE` en `STORED_UNCLEANED` zijn alleen
  verwijderbaar.
- Records worden atomisch vervangen. Proceslocking wordt uitgesteld totdat een GUI of andere
  tweede actor daadwerkelijk gelijktijdige opdrachten kan geven.
- Na volledige geverifieerde cleanup of expliciet discard verdwijnen record en snapshot. De
  succesvolle ronde blijft aantoonbaar in PostGIS; de lifecyclemetadata is geen extra auditlog.

## Alternatieven

- Alleen het oorspronkelijke zonepad bewaren is afgewezen omdat dit geen inhoud vastzet.
- Alleen een digest bewaren en wijzigingen blokkeren is afgewezen omdat de originele bytes dan
  niet beschikbaar blijven voor herstel.
- Geometrie in het state-record serialiseren is afgewezen wegens onnodige normalisatie en
  herschrijfcomplexiteit.
- Lifecycle in PostGIS opslaan is afgewezen omdat juist rondes die Storage nog niet bereiken
  herstelmetadata nodig hebben.
- Een database, daemon, eventbus of GoF-State-klassen zijn disproportioneel voor één lokale Pi.

## Gevolgen

Een actieve ronde heeft tijdelijk twee extra private bestanden. Hervatten is reproduceerbaar en
toestandsspecifiek. Beschadigde metadata vereist expliciete operatoractie in plaats van een
mogelijk ruimer fallbackbeleid.
De implementatie verwijdert beide bestanden na succes of discard, behoudt ze bij herstelbare
fouten en weigert gewijzigde, ontbrekende of permissieve lifecyclemetadata gesloten.
