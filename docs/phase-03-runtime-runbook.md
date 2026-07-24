# Fase 3 runtime-runbook

Dit runbook verwerkt precies één tijdelijke Collection-buffer via Ingestion en Processing naar
geverifieerde PostgreSQL/PostGIS-opslag. Alleen de Collection-buffer gebruikt SQLite. De CLI toont
uitsluitend aantallen en veilige afwijzingscategorieën.

## Lokale invoer voorbereiden

Runtimebestanden staan onder `data/local`, `data/smoke` en `data/processed` en worden niet
gecommit.

```bash
mkdir -p data/local data/smoke
```

Plaats een lokaal goedgekeurd zonebestand in `data/local/zones.geojson`. Het bestand:

- is een GeoJSON `FeatureCollection` zonder `crs`-member; GeoJSON wordt als WGS84 geïnterpreteerd;
- bevat uitsluitend `Polygon`- of `MultiPolygon`-features;
- bevat per feature een unieke, niet-lege `properties.zone_id`;
- bevat geen overlappende of elkaar rakende zones;
- omvat het geplande meetgebied.

Maak per meetronde een cryptografisch secret van 32 bytes. `umask 077` zorgt dat het bestand
direct met rechten `600` wordt aangemaakt.

```bash
ROUND_ID="phase3-runtime-$(date -u +%Y%m%dT%H%M%SZ)"
SECRET_PATH="data/local/${ROUND_ID}.secret"

umask 077
openssl rand -hex 32 > "$SECRET_PATH"
stat -c 'Secret-rechten: %a' "$SECRET_PATH"
```

Verwacht `Secret-rechten: 600`. Het secret mag uit precies één UTF-8-regel van minimaal 32 tekens
bestaan. Geef het nooit als CLI-argumentwaarde door en toon de inhoud niet.

## Collection uitvoeren

Start vanaf een dedicated adapter in managed mode. Collection regelt monitor mode en herstel
automatisch.

```bash
SOURCE_DB="data/smoke/${ROUND_ID}.sqlite"

sudo -n /home/cyberbrein/poc/.venv/bin/python \
  -m cyberbrein.collection \
  --interface wlan1 \
  --database-path "$SOURCE_DB" \
  --measurement-round-id "$ROUND_ID" \
  --channels 36,40,44,48 \
  --duration 60 \
  --gpsd \
  --require-gps-fix
```

Ga alleen verder bij exitcode `0`, een duidelijk bruikbaar aantal waarnemingen en geen
structureel ontbrekende GPS-fixes.

## PostGIS-configuratie

De lokale database gebruikt de Unix-socket en peer-authenticatie. Zet de URL alleen in de
runtimeomgeving; er staat geen databasewachtwoord in Git of een CLI-argument.

```bash
export CYBERBREIN_DATABASE_URL="postgresql+psycopg2:///cyberbrein_poc"
```

De database bevat maximaal één nog niet verwijderde meetronde. Eén meetronde mag meerdere
goedgekeurde zones bevatten.

## Pipeline uitvoeren

De pipeline vereist dat de ruwe buffer rechten `600` heeft. Gebruik voor de definitieve run de
cleanupvlag; zonder deze vlag blijven bronbuffer en secret beschikbaar voor herstel.

```bash
sudo -n /home/cyberbrein/poc/.venv/bin/python \
  -m cyberbrein.pipeline \
  --source-db "$SOURCE_DB" \
  --measurement-round-id "$ROUND_ID" \
  --zones data/local/zones.geojson \
  --secret-file "$SECRET_PATH" \
  --max-gps-accuracy 15 \
  --delete-source-on-success
```

De uitvoer bevat uitsluitend:

- aantallen geaccepteerde en afgewezen Ingestion-regels;
- veilige Ingestion-redenen;
- aantallen geaccepteerde en afgewezen Processing-regels;
- veilige Processing-redenen;
- het aantal opgeslagen netwerkvondsten;
- bevestiging van opslagverificatie en cleanup.

De CLI toont nooit BSSID, SSID, secret, gepseudonimiseerde netwerk-ID of coördinaten.

## Veilige eindcontrole

```bash
test ! -e "$SOURCE_DB" && echo "Bronbuffer verwijderd"
test ! -e "$SECRET_PATH" && echo "Secret verwijderd"

psql -d cyberbrein_poc -v ON_ERROR_STOP=1 -c "
SELECT
  (SELECT count(*) FROM network_finding) AS netwerkvondsten,
  (SELECT count(*) FROM score_factor) AS scorefactoren,
  NOT EXISTS (
    SELECT 1
    FROM network_score
    WHERE total_points NOT BETWEEN 0 AND 8
       OR (total_points BETWEEN 0 AND 2 AND score_color <> 'GREEN')
       OR (total_points BETWEEN 3 AND 5 AND score_color <> 'YELLOW')
       OR (total_points BETWEEN 6 AND 8 AND score_color <> 'RED')
  ) AS geldige_scores;
"
```

Verwacht een verwijderde bronbuffer en secret, drie scorefactoren per netwerkvondst en
`geldige_scores = t`. Toon geen inhoudelijke rijen uit Storage tijdens de rooktest.

## Fouten en herstel

- Exitcode `2`: ongeldige runtimeconfiguratie of onveilige bestanden.
- Exitcode `3`: Ingestion, Processing, Storage of opslagverificatie is mislukt.
- Exitcode `4`: Storage is geverifieerd, maar cleanup is niet volledig geslaagd.
- Bij exitcode `2` of `3` worden bronbuffer en secret niet verwijderd.
- Bij exitcode `4` moet expliciet worden vastgesteld welke invoer nog bestaat; meld de run niet
  als volledig afgerond.
- SQLite-sidecars `-journal`, `-wal` en `-shm` worden, indien aanwezig, samen met de bronbuffer
  verwijderd.
