# Fase 3 runtime-runbook

Dit runbook verwerkt precies één tijdelijke Collection-buffer via Ingestion en Processing naar
geverifieerde PostgreSQL/PostGIS-opslag. Alleen de Collection-buffer gebruikt SQLite. De CLI toont
uitsluitend aantallen en veilige afwijzingscategorieën.

## Aanbevolen: volledige workflow met één commando

Kopieer bij de eerste ingebruikname `.env.example` naar `.env`, stel minimaal
`CYBERBREIN_INTERFACE` in en plaats het goedgekeurde zonebestand op het geconfigureerde pad. Start
daarna de eenmalige monitorconfiguratie. De managementadapter (standaard `wlan0`) wordt expliciet
beschermd; alleen de capture-adapter wordt unmanaged en bij elke boot in monitor mode gezet. Na
loskoppelen en opnieuw aansluiten activeert een udev-regel dezelfde monitorservice opnieuw.

```bash
sudo ./cyberbrein setup-monitor --interface wlan1
```

Controleer dat dit commando succesvol eindigt. Start daarna Collection, Pipeline en het dashboard
samen met:

```bash
./cyberbrein run
```

Start de launcher zelf zonder `sudo`. Bij de start van Collection vraagt de launcher eenmaal om
het sudo-wachtwoord; Pipeline en het dashboard draaien daarna weer als de normale gebruiker.
`./cyberbrein run` weigert in de standaard `persistent-monitor`-modus een adapter die niet al in
monitor mode staat, voordat runtimebestanden worden gemaakt. Daardoor wordt configuratiedrift niet
stilzwijgend tijdens een meetronde hersteld.

De launcher maakt zelf een UTC-meetronde-ID, cryptografisch mode-600-secret, mode-600-snapshot van
de gevalideerde zones en een klein mode-600-lifecycle-record. Alleen Collection draait via `sudo`;
Pipeline en Streamlit blijven onder de normale gebruiker draaien. De snapshot en het record
bevatten geen waarnemingen, BSSID, SSID, secret of netwerk-ID. Ze zetten voor een actieve ronde wel
exact de zonebytes en de gekozen maximale GPS-nauwkeurigheid vast.

Na geverifieerde opslag verwijdert Pipeline de bronbuffer en het secret; de launcher verwijdert
daarna de zonesnapshot en het lifecycle-record voordat het dashboard start. Bij een fout vóór de
eerste waarneming verwijdert de launcher de volledige ongebruikte runtimebundel automatisch. Als
Collection wel gegevens heeft opgeslagen, blijft de bundel staan en kan Pipeline worden hervat
met het getoonde `./cyberbrein resume <meetronde-id>`-commando.

Voor rondes met lifecyclemetadata gebruikt `resume` altijd het vastgezette beleid. Latere
wijzigingen aan `.env` of het oorspronkelijke zonebestand hebben geen invloed; expliciete
`--zones`- of `--max-gps-accuracy`-overrides worden geweigerd. Dit voorkomt dat dezelfde ruwe
waarnemingen onder een ruimer of anders afgebakend beleid worden verwerkt. Een oudere bewaarde
ronde zonder record en snapshot blijft hervatbaar met het oude flag-/omgevingsgedrag.

Vóór Collection controleert de launcher dat GPSD een 3D-fix mét horizontale nauwkeurigheid binnen
`CYBERBREIN_MAX_GPS_ACCURACY` levert. Pipeline weigert een meetronde zonder bruikbare vondsten en
behoudt in dat geval buffer en secret; zo wordt onbruikbare ruwe invoer niet als succes opgeruimd.
Collection gebruikt dezelfde nauwkeurigheidsgrens, houdt één onderbreekbare GPSD-verbinding open
en rapporteert afzonderlijk ontbrekende fixes, ontbrekende nauwkeurigheid en overschrijdingen.

Gebruik `./cyberbrein run --no-dashboard` om na verwerking te stoppen, of
`./cyberbrein dashboard` om alleen het dashboard opnieuw te starten. Alle waarden uit `.env`
kunnen voor een eenmalige run met CLI-opties worden overschreven; bekijk die met
`./cyberbrein run --help`.

De losse stappen hieronder blijven beschikbaar voor diagnose en gecontroleerd herstel.

## Lokale invoer voorbereiden

Runtimebestanden staan onder `data/local`, `data/smoke` en `data/processed` en worden niet
gecommit. De launcher dwingt voor `data/local` en `data/smoke` mode `700` af.

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

Start vanaf de vooraf geconfigureerde dedicated adapter in monitor mode. Collection laat deze
adapter na afloop in monitor mode staan.

```bash
SOURCE_DB="data/smoke/${ROUND_ID}.sqlite"

sudo -n /home/cyberbrein/poc/.venv/bin/python \
  -m cyberbrein.collection \
  --interface wlan1 \
  --database-path "$SOURCE_DB" \
  --measurement-round-id "$ROUND_ID" \
  --channels 36,40,44,48 \
  --duration 60 \
  --no-auto-monitor \
  --gpsd \
  --require-gps-fix
```

Ga alleen verder bij exitcode `0`, een duidelijk bruikbaar aantal waarnemingen en geen
structureel ontbrekende GPS-fixes.

Voor tijdelijke compatibiliteit kan `CYBERBREIN_INTERFACE_LIFECYCLE=temporary` worden gebruikt.
In die modus schakelt Collection de adapter per run van managed naar monitor en terug. De
veiligheidscontrole gebruikt uitsluitend de lokale IPv4/IPv6-routingtabel en werkt dus ook zonder
internetverbinding. Persistent monitor mode blijft aanbevolen voor dedicated adapters.

Om een capture-adapter weer aan NetworkManager terug te geven:

```bash
sudo ./cyberbrein teardown-monitor --interface wlan1
```

## PostGIS-configuratie

De lokale database gebruikt de Unix-socket en peer-authenticatie. Zet de URL alleen in de
runtimeomgeving; er staat geen databasewachtwoord in Git of een CLI-argument.

```bash
export CYBERBREIN_DATABASE_URL="postgresql+psycopg2:///cyberbrein_poc"
```

De database bevat maximaal één nog niet verwijderde meetronde. Eén meetronde mag meerdere
goedgekeurde zones bevatten. `./cyberbrein run` controleert dit read-only vóór interface-, GPS- en
Collection-acties. Bij een bestaande ronde start geen nieuwe meting; open het dashboard en
verwijder de ronde alleen wanneer de inzichtverstrekking is afgerond. Als Storage niet bereikbaar
is, stopt dezelfde preflight eveneens zonder runtimebestanden te maken.

## Pipeline uitvoeren

De pipeline vereist dat de ruwe buffer rechten `600` heeft. Gebruik voor de definitieve run de
cleanupvlag; zonder deze vlag blijven bronbuffer en secret beschikbaar voor herstel.

```bash
/home/cyberbrein/poc/.venv/bin/python \
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
- Exitcode `5`: de bronbuffer is geldig, maar bevat bij de gekozen beleidsgrens geen bruikbare
  waarnemingen. Hervatten met dezelfde grens kan dit niet oplossen.
- Bij exitcode `2` of `3` worden bronbuffer en secret niet verwijderd.
- Bij exitcode `5` blijven bronbuffer en secret staan. Controleer de meetronde-ID en verwijder ze
  daarna expliciet met `./cyberbrein discard <meetronde-id> --yes`.
- Bij exitcode `4` is Storage geverifieerd, maar is cleanup onvolledig. Voer de verwerking niet
  opnieuw uit. Bekijk de opgeslagen resultaten met `./cyberbrein dashboard`, controleer de door de
  launcher genoemde resterende paden en verwijder de tijdelijke invoer daarna met
  `./cyberbrein discard <meetronde-id> --yes`.
- SQLite-sidecars `-journal`, `-wal` en `-shm` worden, indien aanwezig, samen met de bronbuffer
  verwijderd.
