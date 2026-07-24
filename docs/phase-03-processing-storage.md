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

Een Processing-run gebruikt standaard maximaal 15 meter GPS-onnauwkeurigheid. Een waarneming is alleen
bruikbaar als deze een 3D-fix (`gps_mode >= 3`) en een eindige, niet-negatieve
`gps_accuracy_m` binnen die grens heeft.

Zones zijn vooraf goedgekeurde polygonen in WGS84 (`EPSG:4326`) met een stabiele zone-ID. Een punt
op de buitenrand telt als onderdeel van de zone. Als een punt door overlappende zones aan meer dan
één zone gekoppeld kan worden, wordt het als ambigu afgewezen; Processing kiest nooit stilzwijgend
een zone.

## Normalisatie en aggregatie

Encryptie wordt voor aggregatie genormaliseerd naar één van:

- `OPEN`;
- `OUTDATED`;
- `WPA2`;
- `WPA3`;
- `ENTERPRISE`;
- `UNKNOWN`.

WPA1 en WEP vallen beide onder `OUTDATED` en vormen geen afzonderlijke scorecategorie. Enterprise
wordt herkend aan Enterprise-, EAP- of 802.1X-aanduidingen. Gemengde aanduidingen krijgen de
sterkste herkende beveiligingscategorie. Onbekende of lege waarden worden `UNKNOWN`. Deze
normalisatie beschrijft alleen wat in het frame is geadverteerd en is geen bewijs dat een
configuratie veilig is.

Waarnemingen worden gegroepeerd op `(measurement_round_id, zone_id, network_id)`. Daardoor blijft
zichtbaar dat hetzelfde gepseudonimiseerde netwerk in meerdere zones is waargenomen.

De gemiddelde RSSI wordt over alle gegroepeerde waarnemingen berekend. De sterkste RSSI en de
representatieve meting komen uit de waarneming met de hoogste RSSI. Bij gelijke RSSI wint de vroegste
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

De exposurescore volgt tabellen 20 tot en met 22 uit het afstudeerverslag. Iedere netwerkvondst
heeft exact drie factoren met een bijdrage van 0, 1 of 2:

- signaalsterkte, gewicht 1: RSSI onder -80 dBm geeft 0, -80 tot en met -67 dBm geeft 1 en
  sterker dan -67 dBm geeft 2;
- encryptietype, gewicht 2: WPA2, WPA3 of Enterprise geeft 0, verouderd of onbekend geeft 1 en
  open geeft 2;
- waarnemingsfrequentie, gewicht 1: één waarneming geeft 0, 2 tot en met 9 geeft 1 en 10 of meer
  geeft 2.

De formule is:

```text
total_points =
    (signal_contribution * 1)
  + (encryption_contribution * 2)
  + (frequency_contribution * 1)
```

De totaalscore loopt van 0 tot en met 8. Score 0-2 is groen, 3-5 is geel en 6-8 is rood. Storage
bewaart per factor de bijdrage, weging en gewogen punten, plus totaalscore en kleur. De score is
een uitlegbare prioritering binnen deze PoC en geen bewijs dat een netwerk kwetsbaar is.
`ssid_present` blijft privacyveilige metadata, maar is nadrukkelijk geen scorefactor.

De frequentiedrempels gelden voor de gestandaardiseerde hardwaretest van 60 seconden, kanalen
36, 40, 44 en 48 en een dwell-tijd van één seconde. Runs met andere meetinstellingen zijn niet
zonder meer scorematig vergelijkbaar.
