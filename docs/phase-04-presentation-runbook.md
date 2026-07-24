# Fase 4: PostGIS en Presentation

Dit runbook richt de normale PostgreSQL/PostGIS-opslag en het lokale Streamlit-dashboard in.
SQLite blijft uitsluitend de tijdelijke bronbuffer van Collection. Het dashboard wordt niet
publiek aangeboden en er is bewust geen permanente systemd-service ingericht.

## Eenmalige database-inrichting

De Raspberry Pi gebruikt PostgreSQL 17 en PostGIS 3.5. Maak een herstelkopie van de
authenticatieconfiguratie voordat deze wordt aangepast:

```bash
sudo cp /etc/postgresql/17/main/pg_hba.conf \
  /tmp/pg_hba.conf.cyberbrein-backup
```

Voeg vóór de algemene lokale authenticatieregel deze beperkte peer-regel toe:

```text
local   cyberbrein_poc  cyberbrein  peer
```

Maak daarna een lokale rol en database. Deze stappen zijn eenmalig; voer `createuser` en
`createdb` niet opnieuw uit wanneer rol en database al bestaan.

```bash
sudo -u postgres createuser cyberbrein
sudo -u postgres createdb --owner=cyberbrein cyberbrein_poc
sudo -u postgres psql -d cyberbrein_poc -c "CREATE EXTENSION postgis;"
sudo -u postgres psql -c "SELECT pg_reload_conf();"
```

Controleer zonder wachtwoord of geheim:

```bash
psql -d cyberbrein_poc -Atqc \
  "SELECT current_user, current_database(), PostGIS_Version();"
```

Verwacht gebruiker `cyberbrein`, database `cyberbrein_poc` en een PostGIS-versie. De applicatie
gebruikt uitsluitend de lokale Unix-socket; TCP-toegang of een publiek luisteradres is niet nodig.

Maak voor lokale integratietests daarnaast een strikt gescheiden database:

```bash
sudo -u postgres createdb --owner=cyberbrein cyberbrein_test
sudo -u postgres psql -d cyberbrein_test -c "CREATE EXTENSION postgis;"
```

De tests weigeren uit veiligheid iedere database waarvan de naam niet eindigt op `_test`.

## Meetronden en zones

De normale database bevat maximaal één nog niet verwijderde meetronde. Een andere ronde wordt
geweigerd zodat bestaande resultaten niet stilzwijgend verdwijnen.

Eén meetronde mag meerdere niet-overlappende goedgekeurde zones bevatten. Gebruik voor één
bedrijventerrein en één rapportagedoel:

- één `measurement_round_id`;
- één GeoJSON-bestand met bijvoorbeeld `zone-a` en `zone-b`;
- één tijdelijke Collection-buffer waarin beide scans onder dezelfde meetronde worden verzameld;
- één pipeline-run nadat beide zones zijn gemeten.

Gebruik afzonderlijke meetronden wanneer meetdoel, meetmoment, privacyplan of rapportagecontext
verschilt. Het dashboard kan binnen één ronde op zone filteren.

## Pipeline naar PostGIS

Zet de database-URL in de runtimeomgeving. De URL bevat bij peer-authenticatie geen wachtwoord:

```bash
export CYBERBREIN_DATABASE_URL="postgresql+psycopg2:///cyberbrein_poc"
```

Voer de pipeline uit volgens `phase-03-runtime-runbook.md`. De standaard GPS-grens is 15 meter.
De pipeline bewaart:

- de meetronde en status;
- een PostGIS-zonepolygoon met SRID 4326;
- een indicatief displaypunt met SRID 4326 per netwerkvondst;
- gemiddelde en sterkste RSSI;
- één actuele exposure-score;
- exact drie uitlegbare scorefactoren.

Originele BSSID, ruwe SSID, meetrondesecret en losse ruwe observaties komen niet in PostGIS.

## Dashboard starten

Start het dashboard handmatig en bind alleen aan localhost:

```bash
export CYBERBREIN_DATABASE_URL="postgresql+psycopg2:///cyberbrein_poc"
.venv/bin/streamlit run src/cyberbrein/presentation/app.py \
  --server.address 127.0.0.1 \
  --server.port 8501 \
  --server.headless true
```

Open daarna lokaal `http://127.0.0.1:8501`. Stop het dashboard met `Ctrl+C`.

De kaart gebruikt CARTO Light zonder labels, met wegen uit OpenStreetMap maar zonder straatnamen,
bedrijfsnamen of adressen. De browser vraagt de zichtbare kaarttegels rechtstreeks bij CARTO op;
meetdata en netwerk-ID's worden niet aan de tegelprovider doorgegeven. Dicht bij elkaar liggende
vondsten worden bij uitzoomen geclusterd. Exact overlappende vondsten waaieren bij selectie tijdelijk
uit, zonder opgeslagen displaypunten te veranderen.

Filters zijn beschikbaar voor zone, band, kanaal, encryptietype, scorekleur en signaalklasse. Een
pseudonieme netwerk-ID en de scorefactoren verschijnen pas na bewuste selectie van een bolletje.
Numerieke coördinaten worden niet getoond.

## PDF-preview

Klik op **Maak PDF-preview**. De preview:

- volgt de actieve dashboardfilters;
- bevat de labelloze kaart, aantallen, scorekleuren en drie scorefactoren;
- gebruikt generieke vondstnummers en geen pseudonieme netwerk-ID;
- bevat geen BSSID, SSID, bedrijfsnaam, adres of numerieke coördinaten;
- blijft alleen in het geheugen totdat de gebruiker expliciet op **Download PDF** klikt.

Een exportfout verandert de opgeslagen data niet en maakt het dashboard niet onbruikbaar.

## Veilige controles

Controleer alleen schema en aantallen, niet de inhoudelijke rijen:

```bash
psql -d cyberbrein_poc -v ON_ERROR_STOP=1 -c "
SELECT
  (SELECT count(*) FROM measurement_round) AS meetronden,
  (SELECT count(*) FROM zone) AS zones,
  (SELECT count(*) FROM network_finding) AS netwerkvondsten,
  (SELECT count(*) FROM network_score) AS scores,
  (SELECT count(*) FROM score_factor) AS scorefactoren;
"
```

De verhouding `scorefactoren = netwerkvondsten * 3` moet gelden. De geometrykolommen zijn
`zone.polygon` en `network_finding.display_point`, beide met SRID 4326 en een GiST-index.

## Nog niet in deze fase

FR-10 volgt als aparte Operations-stap na acceptatie van het dashboard. Die stap voegt de
verwijderbevestiging, hard delete, controlequery en een privacyveilig activiteitenlog toe.
