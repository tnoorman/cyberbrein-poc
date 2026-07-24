# Fase 3 runtime-runbook

Dit runbook verwerkt precies één tijdelijke Collection-buffer via Ingestion en Processing naar
geverifieerde SQLite-opslag. De CLI toont uitsluitend aantallen en veilige afwijzingscategorieën.

## Lokale invoer voorbereiden

Runtimebestanden staan onder `data/local`, `data/smoke` en `data/processed` en worden niet
gecommit.

```bash
mkdir -p data/local data/smoke data/processed
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

## Pipeline uitvoeren

De pipeline vereist dat de ruwe buffer rechten `600` heeft. Gebruik voor de definitieve run de
cleanupvlag; zonder deze vlag blijven bronbuffer en secret beschikbaar voor herstel.

```bash
STORAGE_DB="data/processed/${ROUND_ID}.sqlite"

sudo -n /home/cyberbrein/poc/.venv/bin/python \
  -m cyberbrein.pipeline \
  --source-db "$SOURCE_DB" \
  --measurement-round-id "$ROUND_ID" \
  --zones data/local/zones.geojson \
  --secret-file "$SECRET_PATH" \
  --storage-db "$STORAGE_DB" \
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
stat -c 'Storage-rechten: %a' "$STORAGE_DB"
test ! -e "$SOURCE_DB" && echo "Bronbuffer verwijderd"
test ! -e "$SECRET_PATH" && echo "Secret verwijderd"

sudo -n /home/cyberbrein/poc/.venv/bin/python -c '
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as connection:
    findings = connection.execute("SELECT COUNT(*) FROM network_findings").fetchone()[0]
    factors = connection.execute("SELECT COUNT(*) FROM score_factors").fetchone()[0]
    invalid_scores = connection.execute("""
        SELECT COUNT(*)
        FROM network_findings
        WHERE score NOT BETWEEN 0 AND 8
           OR (score BETWEEN 0 AND 2 AND attention_level != 'GREEN')
           OR (score BETWEEN 3 AND 5 AND attention_level != 'YELLOW')
           OR (score BETWEEN 6 AND 8 AND attention_level != 'RED')
    """).fetchone()[0]
print("Netwerkvondsten:", findings)
print("Scorefactoren:", factors)
print("Drie factoren per vondst:", factors == findings * 3)
print("Ongeldige score/kleur-combinaties:", invalid_scores)
' "$STORAGE_DB"
```

Verwacht Storage-rechten `600`, een verwijderde bronbuffer en secret, en alleen numerieke
opslagtellingen. `Drie factoren per vondst` moet `True` zijn en het aantal ongeldige
score/kleur-combinaties moet `0` zijn. Toon geen inhoudelijke rijen uit Storage tijdens de
rooktest.

## Fouten en herstel

- Exitcode `2`: ongeldige runtimeconfiguratie of onveilige bestanden.
- Exitcode `3`: Ingestion, Processing, Storage of opslagverificatie is mislukt.
- Exitcode `4`: Storage is geverifieerd, maar cleanup is niet volledig geslaagd.
- Bij exitcode `2` of `3` worden bronbuffer en secret niet verwijderd.
- Bij exitcode `4` moet expliciet worden vastgesteld welke invoer nog bestaat; meld de run niet
  als volledig afgerond.
- SQLite-sidecars `-journal`, `-wal` en `-shm` worden, indien aanwezig, samen met de bronbuffer
  verwijderd.
