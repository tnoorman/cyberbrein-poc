# Fase 3: Processing en Storage

Dit document legt de keuzes vast waarmee Processing deterministisch kan worden gebouwd. Het
verandert de privacygrenzen uit `architecture-boundaries.md` niet.

## Invoer en frequenties

Processing accepteert uitsluitend `AcceptedObservation`-objecten uit Ingestion. Ruwe BSSID's,
SSID's, secrets en tijdelijke SQLite-data blijven buiten Processing.

De ondersteunde frequentiebanden blijven gelijk aan het Ingestion-contract:

- 2,4 GHz: `2400 <= frequency_mhz < 2500`;
- 5 GHz: `5000 <= frequency_mhz < 5900`.

Een ontbrekende frequentie mag door wanneer kanaal en band geldig zijn. Een aanwezige frequentie
buiten deze grenzen, of een frequentie die niet met de opgegeven band overeenkomt, wordt veilig
afgewezen. Ondersteuning voor 6 GHz vereist later een expliciete contractwijziging in Collection,
Ingestion en Processing samen.

## GPS-kwaliteit en zones

Een Processing-run krijgt een expliciete maximale GPS-onnauwkeurigheid. Een waarneming is alleen
bruikbaar als deze een 3D-fix (`gps_mode >= 3`) en een eindige, niet-negatieve
`gps_accuracy_m` binnen die grens heeft.

Zones zijn vooraf goedgekeurde polygonen in WGS84 (`EPSG:4326`) met een stabiele zone-ID. Een punt
op de buitenrand telt als onderdeel van de zone. Als een punt door overlappende zones aan meer dan
één zone gekoppeld kan worden, wordt het als ambigu afgewezen; Processing kiest nooit stilzwijgend
een zone.

## Normalisatie en aggregatie

Encryptie wordt voor aggregatie genormaliseerd naar één van:

- `OPEN`;
- `WEP`;
- `WPA`;
- `WPA2`;
- `WPA3`;
- `UNKNOWN`.

Gemengde aanduidingen krijgen de sterkste herkende beveiligingscategorie. Onbekende of lege
waarden worden `UNKNOWN`. Deze normalisatie beschrijft alleen wat in het frame is geadverteerd en
is geen bewijs dat een configuratie veilig is.

Waarnemingen worden gegroepeerd op `(measurement_round_id, zone_id, network_id)`. Daardoor blijft
zichtbaar dat hetzelfde gepseudonimiseerde netwerk in meerdere zones is waargenomen.

De representatieve meting is de waarneming met de hoogste RSSI. Bij gelijke RSSI wint de vroegste
tijdstempel; een laatste stabiele vergelijking op coördinaten en radio-eigenschappen maakt de
uitkomst onafhankelijk van invoervolgorde. Het displaypunt, RSSI, kanaal, frequentie en band komen
allemaal uit diezelfde meting en vormen dus geen kunstmatige combinatie. Het displaypunt heet in
uitvoer expliciet een representatief meetpunt en nooit een accesspointlocatie.

De encryptiecategorie van een netwerkvondst is de zwakste genormaliseerde categorie die tijdens de
aggregatie is waargenomen. Dit voorkomt dat een zwakkere geadverteerde configuratie door een andere
waarneming wordt verborgen.

## Verwerkingsvolgorde

Processing voert de stappen in deze volgorde uit:

1. controleer Processing-invarianten en frequentie/band-samenhang;
2. filter op GPS-kwaliteit;
3. koppel het meetpunt aan precies één goedgekeurde zone;
4. normaliseer encryptie;
5. aggregeer per meetronde, zone en netwerk;
6. kies de representatieve meting en bereken uitlegbare scorefactoren;
7. lever uitsluitend verwerkte netwerkvondsten aan Storage.

Storage bewaart geen losse waarnemingen. Een opslagtransactie vervangt de resultaten van één
meetronde atomair, zodat een gedeeltelijke run niet als compleet resultaat zichtbaar wordt.

## PoC-score

De exposurescore loopt van 0 tot en met 100 en is de som van vier zichtbare factoren:

- geadverteerde encryptie: `WPA3=0`, `WPA2=10`, `WPA=30`, `WEP=45`, `OPEN=50`,
  `UNKNOWN=40`;
- representatieve signaalsterkte: `30` punten vanaf -50 dBm, `20` vanaf -70 dBm en anders `10`;
- aanwezige SSID: `10` punten, uitsluitend als zichtbaarheidsindicator;
- herhaalde waarneming: `0` punten bij één waarneming, `5` bij 2-9 en `10` vanaf 10.

De score is een uitlegbare prioritering binnen deze PoC, geen bewijs dat een netwerk kwetsbaar is.
De losse factoren worden samen met het totaal opgeslagen zodat Presentation de berekening kan
uitleggen.
