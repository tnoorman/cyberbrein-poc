# Fase 7: defence-readiness-acceptatieresultaten

## Doel en scope

Deze afrondingscontrole brengt de actuele implementatie, architectuurdocumentatie en aantoonbare
testresultaten met elkaar in overeenstemming voordat de verdediging en realisatievideo worden
uitgewerkt. De controle introduceert geen nieuwe architectuurlaag of productiefunctionaliteit.

## Architectuur en runtime

- De CLI-presentatie en `WorkflowService` blijven gescheiden volgens ADR-0002.
- Lifecycletransities, vastgezette zones en GPS-beleid, atomische statevervanging en fail-closed
  herstel blijven geïmplementeerd en getest volgens ADR-0003.
- De architectuurgrens beschrijft nu precies dat Presentation alleen-lezen dashboardqueries doet
  en voor de definitieve verwijderactie Operations aanroept.
- Het handmatige Pipeline-voorbeeld draait, gelijk aan het runtimecontract, als normale gebruiker
  en niet via `sudo`.
- De documentatie benoemt de 5GHz-standaardkanalen, de afwijzing van 6GHz door Ingestion en de
  metadata die een externe CARTO-tegelprovider kan ontvangen.

## Encryptieclassificatie

- Een RSN-frame dat niet verder als WPA2 of WPA3 kan worden onderscheiden en een netwerk dat beide
  varianten aanbiedt, blijven expliciet `WPA2_OR_WPA3` en worden niet meer als uitsluitend WPA3
  gepresenteerd.
- De ambigue categorie behoudt dezelfde nulbijdrage als WPA2 en WPA3 in het bestaande
  exposuremodel; er verandert daardoor geen score op basis van een onbewezen onderscheid.
- Een exception of leeg resultaat bij het lezen van netwerkbeveiligingsmetadata wordt `UNKNOWN`
  en nooit automatisch `OPEN`.
- Aggregatie behoudt bij WPA3 plus een ambigue RSN-waarneming conservatief de ambigue categorie.

## Dependencies en geautomatiseerde verificatie

- `requests`, rechtstreeks gebruikt voor PDF-kaarttegels, staat nu expliciet als dependency.
- Niet rechtstreeks gebruikte top-level dependencies GeoPandas, pandas, Plotly en pyproj zijn
  verwijderd. Dependencies die een bibliotheek zelf nodig heeft, blijven via die bibliotheek
  beheerd.
- `pip check` rapporteert geen gebroken requirements in de lokale projectomgeving.
- Ruff-lint en Ruff-format slagen voor `src` en `tests`.
- De volledige lokale suite tegen PostgreSQL/PostGIS en met Scapy-interface-initialisatie bevat
  286 tests en slaagt volledig.

## PDF-kaart

De PDF-kaart gebruikt een aspectvaste Web Mercator-viewport met een Leaflet-achtige gehele zoom.
Regressietests bevestigen dat de kaart niet wordt uitgerekt, alle databounds bevat en voldoende
zichtbare context rond de meetzone houdt.

## Open praktijkpunt voor de realisatievideo

Voor definitief bewijs van NFR-03 blijft een nieuwe buitenmeting nodig met
`gps_accuracy_m <= 15`. Tijdens die meetronde worden dashboard en PDF nog één keer visueel naast
elkaar gecontroleerd en worden filters, detailweergave, export en geverifieerde verwijdering
doorlopen. Dit is praktijkvalidatie en geen open architectuur- of codewijziging.

## Storage-preflight na praktijkbevinding

Een praktijkrun liet zien dat een nog niet verwijderde meetronde pas tijdens Pipeline als generieke
`storage_failed` zichtbaar werd. De launcher controleert daarom voortaan read-only vóór monitor,
GPS, runtimecreatie en Collection of Storage al een verwerkte ronde bevat. Een bestaande ronde
geeft veilige dashboardinstructies en wordt nooit automatisch verwijderd. Een onbereikbare Storage
faalt eveneens gesloten. De Pipeline houdt daarnaast de specifieke veilige categorie
`active_measurement_round_exists` voor een eventuele race-condition na de preflight.
