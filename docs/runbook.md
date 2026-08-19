# Runbook Cyberbrein Wi-Fi Exposure PoC

| Documentgegeven | Waarde |
|---|---|
| Organisatie | Cyberbrein |
| Systeem | Cyberbrein Wi-Fi Exposure Proof of Concept |
| Documenttype | Operationeel runbook / beroepsproduct |
| Versie | 1.0 |
| Datum | 19 augustus 2026 |
| Eigenaar | Cyberbrein |
| Classificatie | Intern; deel configuratie, meetdata en exports alleen volgens gemaakte afspraken |

## 1. Doel en reikwijdte

Dit runbook beschrijft hoe een bevoegde medewerker de Cyberbrein Wi-Fi Exposure PoC installeert,
configureert en bedient. Na het volgen van dit document kan de medewerker:

1. de PoC en PostgreSQL/PostGIS inrichten;
2. een dedicated Wi-Fi-adapter en GPS-ontvanger controleren;
3. een meetronde uitvoeren;
4. de validatie-, pseudonimiserings- en verwerkingspipeline uitvoeren;
5. de resultaten in het lokale dashboard bekijken en filteren;
6. een PDF-rapport genereren en downloaden;
7. tijdelijke ruwe invoer of verwerkte meetdata gecontroleerd verwijderen;
8. bekende fouten diagnosticeren en veilig herstellen;
9. de technische kwaliteit met dezelfde controles als CI verifiëren.

De PoC verzamelt uitsluitend passieve Wi-Fi-managementframes. De uitkomst is een indicatie van
Wi-Fi-exposure binnen een meetgebied. Een netwerkvondst of indicatief kaartpunt bewijst niet waar
een access point fysiek staat en is geen volledig beveiligingsoordeel.

Dit document gaat uit van de afgesproken Linux-/Raspberry Pi-omgeving met `systemd`,
NetworkManager, een aparte managementadapter, een dedicated monitor-mode-adapter, GPSD en een
lokale PostgreSQL/PostGIS-database. De referentie-implementatie gebruikt PostgreSQL 17 en PostGIS
3.5. Python 3.11 of nieuwer is vereist.

## 2. Koppeling met requirements

| Runbookonderdeel | Doel | Koppeling |
|---|---|---|
| Installatie | PoC opzetten in de afgesproken omgeving | NFR-04, Operations |
| Meetronde starten | Collection uitvoeren met Wi-Fi-adapter en GPS | FR-01 |
| Pipeline draaien | Data valideren, pseudonimiseren, verwerken en opslaan | FR-02 t/m FR-06 |
| Dashboard openen | Resultaten bekijken op kaart en in detailweergave | FR-07, FR-08 |
| PDF exporteren | Meetresultaten delen zonder ruwe identifiers | FR-09 |
| Meetdata verwijderen | Actieve meetronde opschonen na inzichtverstrekking | FR-10 |
| Problemen oplossen en controles | Bekende fouten, herstel en kwaliteitscontroles beschrijven | NFR-04, NFR-05 |

## 3. Systeemoverzicht

De normale gegevensstroom is:

```text
Wi-Fi-adapter + GPSD
        |
        v
Collection -> tijdelijke afgeschermde SQLite-buffer
        |
        v
Ingestion -> validatie + pseudonimisering met een tijdelijk meetrondesecret
        |
        v
Processing -> deduplicatie + GPS-controle + zonekoppeling + exposure-score
        |
        v
PostgreSQL/PostGIS -> maximaal één nog niet verwijderde meetronde
        |
        +--> lokaal Streamlit-dashboard
        +--> PDF-export in sessiegeheugen
        +--> gecontroleerde hard delete via Operations
```

Belangrijke ontwerpgrenzen:

- SQLite is alleen de tijdelijke Collection-buffer; het is niet de normale resultaatopslag.
- PostgreSQL/PostGIS bevat verwerkte meetrondegegevens, zones en scores.
- De originele BSSID, ruwe SSID, het meetrondesecret en losse ruwe observaties komen niet in
  PostGIS.
- Alleen Collection draait met verhoogde rechten. Pipeline en dashboard draaien als de normale
  gebruiker.
- De launcher verwijdert ruwe invoer pas na geverifieerde opslag, of na een expliciet bevestigd
  `discard`.
- De database bevat maximaal één nog niet verwijderde meetronde. Een nieuwe run overschrijft een
  bestaande ronde nooit automatisch.
- Het dashboard bindt standaard alleen aan `127.0.0.1` en heeft geen applicatieauthenticatie.

## 4. Rollen en verantwoordelijkheden

| Rol | Verantwoordelijkheden |
|---|---|
| Systeembeheerder | Linux-pakketten, projectaccount, PostgreSQL/PostGIS, GPSD en eenmalige monitor-mode-inrichting |
| Uitvoerder meetronde | Toestemming en meetgebied controleren, preflight uitvoeren, meetronde starten en uitkomst controleren |
| Inzageverstrekker | Dashboard beoordelen, filters toepassen, bevindingen toelichten en eventueel PDF downloaden |
| Gegevensbeheerder | Na inzichtverstrekking verwerkte meetdata verwijderen en verwijdercontrole uitvoeren |

Eén medewerker kan meerdere rollen vervullen, mits die medewerker daarvoor bevoegd is. Voer geen
meting uit zonder toestemming voor het gekozen gebied en doel.

## 5. Veiligheids- en privacyregels

Houd tijdens alle procedures de volgende regels aan:

1. Werk vanuit het projectaccount en de projectmap. In de referentieomgeving zijn dat gebruiker
   `cyberbrein` en `/home/cyberbrein/poc`.
2. Start `run`, `resume`, `dashboard` en `discard` nooit met `sudo`. De launcher vraagt alleen voor
   Collection om verhoogde rechten.
3. Gebruik nooit de managementinterface als capture-interface. Standaard blijft `wlan0`
   beschikbaar voor netwerktoegang of een access point en is `wlan1` dedicated voor capture.
4. Toon, kopieer of log geen ruwe BSSID's, SSID's, secrets, exacte losse observaties of precieze
   coördinaten.
5. Commit `.env`, bestanden onder `data/`, SQLite-buffers, secrets, logs, PDF-exports en andere
   runtimebestanden niet. Deze paden zijn in `.gitignore` opgenomen.
6. Bind het dashboard alleen aan `127.0.0.1`. Gebruik `0.0.0.0` uitsluitend tijdelijk voor een
   vooraf afgesproken test op een vertrouwd netwerk en stop het dashboard direct daarna.
7. Verwijder verwerkte meetdata pas nadat de inzichten zijn verstrekt en een gewenste PDF veilig
   is opgeslagen.
8. Een gedownloade PDF valt buiten de serveropslag. Beheer en verwijder die kopie volgens de
   afgesproken gegevenscyclus.
9. Maak geen databaseback-up met meetdata tenzij Cyberbrein dat vooraf expliciet heeft toegestaan.
   Een ongecontroleerde back-up doorbreekt de verwijdercyclus.

## 6. Benodigdheden

### 6.1 Hardware

- Linux-/Raspberry Pi-systeem met voldoende voeding en lokale opslag;
- managementinterface, standaard `wlan0`;
- afzonderlijke Wi-Fi-adapter die monitor mode en de gekozen kanalen ondersteunt;
- in de technische proef gebruikte capture-adapter: TP-Link Archer T2U Plus;
- GPS-ontvanger die via GPSD een 3D-fix en horizontale nauwkeurigheid levert;
- in de technische proef gebruikte ontvanger: VK-162;
- bij een buitenmeting: vrije zichtlijn voor de GPS-ontvanger.

Controleer vóór aanschaf of gebruik altijd of de concrete chipset en Linux-driver monitor mode en
de beoogde 5GHz-kanalen ondersteunen. De productnaam alleen garandeert dit niet.

### 6.2 Software

Minimaal nodig:

- Python 3.11 of nieuwer, `venv` en `pip`;
- PostgreSQL en PostGIS; referentieversies 17 en 3.5;
- `gpsd` en GPSD-clienttools;
- `iw`, `iproute2`, NetworkManager, `udev` en `systemd`;
- OpenSSL voor een eventuele handmatige herstelprocedure;
- Git om de broncode op het afgesproken revisieniveau te plaatsen.

Op een Debian-gebaseerd systeem zijn de gebruikelijke pakketnamen als volgt. Controleer eerst of
de goedgekeurde image of interne provisioning deze al levert. De exacte PostgreSQL-/PostGIS-
pakketnaam kan per distributieversie verschillen.

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip git \
  postgresql postgresql-contrib postgis \
  gpsd gpsd-clients iw iproute2 network-manager openssl
```

Controleer de geïnstalleerde versies:

```bash
python3 --version
psql --version
gpsd --version
iw --version
```

### 6.3 Netwerktoegang

De meting en verwerking zelf vereisen geen internetverbinding. Internettoegang kan wel nodig zijn
voor de eerste installatie van Python-pakketten en voor de labelloze CARTO-kaarttegels in het
dashboard en de PDF. Zonder bereikbare tegelserver blijven de meetresultaten bruikbaar, maar kan de
kaartondergrond in de PDF ontbreken.

## 7. Eenmalige installatie

Voer deze paragraaf uit als het project nog niet is geïnstalleerd. Gebruik voor operationele runs
steeds hetzelfde lokale projectaccount; peer-authenticatie koppelt dat account aan de
PostgreSQL-rol.

### 7.1 Project plaatsen en Python-omgeving maken

Plaats of clone de goedgekeurde projectversie in de projectmap en ga naar die map:

```bash
cd /home/cyberbrein/poc
```

Controleer vóór installatie de actieve revisie en lokale wijzigingen:

```bash
git status --short
git rev-parse --short HEAD
```

Maak de virtuele omgeving en installeer de applicatie met operationele dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e .
chmod u+x cyberbrein
```

Installeer voor ontwikkel- en acceptatiecontroles ook de ontwikkeldependencies:

```bash
.venv/bin/pip install -e ".[dev]"
```

Controleer de installatie:

```bash
.venv/bin/python -m pip check
./cyberbrein --help
```

Verwacht bij `pip check` geen gebroken requirements en bij het tweede commando de acties `run`,
`resume`, `dashboard`, `discard`, `setup-monitor` en `teardown-monitor`.

### 7.2 Runtimeconfiguratie maken

Kopieer het voorbeeld en scherm de configuratie af:

```bash
cp .env.example .env
chmod 600 .env
mkdir -p data/local data/smoke data/logs
chmod 700 data/local data/smoke data/logs
```

Open `.env` lokaal en controleer minimaal:

```dotenv
CYBERBREIN_DATABASE_URL=postgresql+psycopg2:///cyberbrein_poc
CYBERBREIN_INTERFACE=wlan1
CYBERBREIN_MANAGEMENT_INTERFACE=wlan0
CYBERBREIN_INTERFACE_LIFECYCLE=persistent-monitor
CYBERBREIN_CHANNELS=36,40,44,48
CYBERBREIN_DURATION=60
CYBERBREIN_ZONES=data/local/zones.geojson
CYBERBREIN_MAX_GPS_ACCURACY=15
CYBERBREIN_DASHBOARD_ADDRESS=127.0.0.1
CYBERBREIN_DASHBOARD_PORT=8501
```

Betekenis van de instellingen:

| Instelling | Betekenis en veilige standaard |
|---|---|
| `CYBERBREIN_DATABASE_URL` | Lokale PostgreSQL/PostGIS-URL via Unix-socket, zonder wachtwoord in het bestand |
| `CYBERBREIN_INTERFACE` | Dedicated capture-interface, bijvoorbeeld `wlan1` |
| `CYBERBREIN_MANAGEMENT_INTERFACE` | Interface die beschikbaar moet blijven voor beheer, standaard `wlan0` |
| `CYBERBREIN_INTERFACE_LIFECYCLE` | `persistent-monitor` aanbevolen; `temporary` alleen voor compatibiliteit |
| `CYBERBREIN_CHANNELS` | Te scannen kanalen; de standaard is de geteste 5GHz-set 36, 40, 44 en 48 |
| `CYBERBREIN_DURATION` | Meetduur in seconden; moet groter dan nul zijn |
| `CYBERBREIN_ZONES` | Pad naar het goedgekeurde GeoJSON-zonebestand |
| `CYBERBREIN_MAX_GPS_ACCURACY` | Hoogst toegestane horizontale GPS-fout in meter, standaard 15 |
| `CYBERBREIN_DASHBOARD_ADDRESS` | Bindadres; houd dit op `127.0.0.1` |
| `CYBERBREIN_DASHBOARD_PORT` | Lokale TCP-poort, standaard 8501 |

De standaardkanaalset is 5GHz. Ingestion wijst 6GHz-waarnemingen af. Verander kanalen alleen als
de adapter, het meetplan en de privacyafspraken dit ondersteunen.

### 7.3 PostgreSQL/PostGIS inrichten

Deze procedure veronderstelt dat het Linux-account `cyberbrein` heet. Gebruik een andere rol of
peer-mapping als Cyberbrein bewust een andere accountnaam heeft gekozen.

Maak eerst een herstelkopie van de PostgreSQL-authenticatieconfiguratie. Pas het versienummer in
het pad aan als de geïnstalleerde hoofdversie anders is:

```bash
sudo cp /etc/postgresql/17/main/pg_hba.conf \
  /tmp/pg_hba.conf.cyberbrein-backup
```

Plaats vóór de algemene lokale authenticatieregel in `pg_hba.conf`:

```text
local   cyberbrein_poc  cyberbrein  peer
```

Maak daarna eenmalig de rol, database en extensie. Sla `createuser` of `createdb` over als het
object aantoonbaar al bestaat:

```bash
sudo -u postgres createuser cyberbrein
sudo -u postgres createdb --owner=cyberbrein cyberbrein_poc
sudo -u postgres psql -d cyberbrein_poc -c "CREATE EXTENSION postgis;"
sudo -u postgres psql -c "SELECT pg_reload_conf();"
```

Controleer vanuit het gewone projectaccount de wachtwoordloze lokale verbinding:

```bash
psql -d cyberbrein_poc -Atqc \
  "SELECT current_user, current_database(), PostGIS_Version();"
```

Verwacht `cyberbrein`, `cyberbrein_poc` en een PostGIS-versie. De applicatie heeft geen TCP-
toegang of publiek luisteradres nodig.

Maak alleen wanneer lokale integratietests nodig zijn een strikt gescheiden testdatabase:

```bash
sudo -u postgres createdb --owner=cyberbrein cyberbrein_test
sudo -u postgres psql -d cyberbrein_test -c "CREATE EXTENSION postgis;"
```

De integratietests weigeren uit veiligheid een database waarvan de naam niet op `_test` eindigt.

### 7.4 GPSD inrichten en controleren

Bepaal eerst het stabiele devicepad van de GPS-ontvanger:

```bash
ls -l /dev/serial/by-id/
```

Configureer GPSD volgens de beheerde Linux-image met dit devicepad en activeer GPSD. Op een
Debian-gebaseerde installatie is de gebruikelijke controle:

```bash
sudo systemctl enable --now gpsd.socket
systemctl status gpsd.socket --no-pager
gpspipe -w -n 10
```

Controleer buiten of bij vrij zicht dat GPSD een 3D-fix, latitude/longitude en horizontale
nauwkeurigheid levert. De workflow weigert te starten als er geen actuele 3D-fix is, als de
nauwkeurigheid ontbreekt of als deze groter is dan de ingestelde grens van standaard 15 meter.
Kopieer de GPS-uitvoer niet naar externe systemen: deze kan precieze coördinaten bevatten.

### 7.5 Zonebestand plaatsen en controleren

Plaats het vooraf goedgekeurde zonebestand op het geconfigureerde pad:

```text
data/local/zones.geojson
```

Het bestand moet aan alle volgende voorwaarden voldoen:

- rootobject is een GeoJSON `FeatureCollection`;
- er is geen `crs`-member; de coördinaten worden als WGS84 geïnterpreteerd;
- iedere feature is een `Polygon` of `MultiPolygon`;
- iedere feature heeft een unieke, niet-lege `properties.zone_id`;
- zones overlappen en raken elkaar niet;
- de zones omvatten het afgesproken meetgebied.

Scherm het bestand af en laat de ingebouwde validator het vóór de eerste echte meetronde
controleren:

```bash
chmod 600 data/local/zones.geojson
./cyberbrein run --help
```

De launcher valideert het bestand opnieuw bij `run`, vóórdat runtimebestanden worden gemaakt. Een
echte `run` mag pas worden gestart wanneer ook toestemming, hardware, GPS en database gereed zijn.

### 7.6 Dedicated Wi-Fi-adapter persistent instellen

Controleer de interfacenamen en zorg dat de capture-interface geen default route of actieve SSH-
sessie draagt:

```bash
iw dev
ip -4 route
ip -6 route
nmcli device status
```

Voer daarna eenmalig uit, met de werkelijke interfacenaam:

```bash
sudo ./cyberbrein setup-monitor --interface wlan1 \
  --management-interface wlan0
```

De setup:

- beschermt de managementinterface;
- maakt uitsluitend de capture-interface unmanaged in NetworkManager;
- installeert een beperkte systemd-template en udev-regel;
- zet de adapter bij boot en na opnieuw aansluiten in monitor mode;
- draait bij een fout de gedeeltelijke configuratie terug.

Controleer de uitkomst:

```bash
iw dev wlan1 info
systemctl is-enabled cyberbrein-monitor@wlan1.service
systemctl status cyberbrein-monitor@wlan1.service --no-pager
```

Verwacht `type monitor` en een ingeschakelde service. Als de adapter later weer voor normaal
netwerkbeheer nodig is, gebruik dan paragraaf 15.2.

## 8. Voorbereiding van iedere meetronde

Voer deze checklist uit voordat de meting begint:

- [ ] Toestemming, doel, locatie, tijdvenster en ontvangers van het resultaat zijn vastgesteld.
- [ ] De projectmap bevat de goedgekeurde revisie en geen onverwachte lokale wijzigingen.
- [ ] `.env` verwijst naar de juiste adapters, kanalen, meetduur, zone en GPS-grens.
- [ ] `data/local/zones.geojson` is de goedgekeurde versie voor deze meetronde.
- [ ] De managementinterface en capture-interface zijn fysiek verschillende adapters.
- [ ] `iw dev wlan1 info` toont in persistent mode `type monitor`.
- [ ] GPSD levert buiten een actuele 3D-fix met horizontale fout van maximaal 15 meter.
- [ ] PostgreSQL/PostGIS is lokaal bereikbaar.
- [ ] Het dashboard bevat geen nog te bewaren vorige meetronde.
- [ ] De systeemklok en tijdzone zijn correct; meetronde-ID's gebruiken UTC.
- [ ] De laptop/Pi heeft voldoende voeding en de operator kan de hele meetduur veilig uitvoeren.

Snelle technische preflight:

```bash
cd /home/cyberbrein/poc
psql -d cyberbrein_poc -Atqc "SELECT PostGIS_Version();"
iw dev wlan1 info
systemctl is-active gpsd.socket
./cyberbrein run --help
```

Bekijk eventueel eerst de huidige opslagstatus zonder inhoudelijke meetdata te tonen:

```bash
psql -d cyberbrein_poc -Atqc "SELECT count(*) FROM measurement_round;"
```

Verwacht `0` voor een nieuwe meetronde. Bij `1` moet de vorige ronde eerst via het dashboard worden
afgerond en verwijderd; verwijder deze nooit alleen om de preflight te omzeilen.

## 9. Meetronde en pipeline uitvoeren

### 9.1 Aanbevolen volledige workflow

Start de launcher als normale gebruiker:

```bash
cd /home/cyberbrein/poc
./cyberbrein run
```

Gebruik dus niet `sudo ./cyberbrein run`. De launcher vraagt tijdens de Collection-stap zelf om
het sudo-wachtwoord. Hij voert achtereenvolgens uit:

1. read-only controle of Storage bereikbaar en leeg is;
2. controle van monitor mode en GPS-kwaliteit;
3. generatie van een UTC-meetronde-ID;
4. generatie van een cryptografisch secret met bestandsrechten `600`;
5. een private snapshot van de gevalideerde zones en het gekozen GPS-beleid;
6. passieve Collection naar een tijdelijke SQLite-buffer;
7. validatie en pseudonimisering;
8. deduplicatie, GPS-controle, zonekoppeling en scoreberekening;
9. opslag in PostgreSQL/PostGIS en terugleesverificatie;
10. verwijdering van buffer, sidecars, secret, zonesnapshot en lifecycle-record;
11. start van het lokale dashboard.

De terminal meldt `Meetronde gestart: <meetronde-id>`. Bewaar alleen het ID dat nodig is voor
herstel; leg geen ruwe terminaldata of precieze waarnemingen vast. De normale uitvoer bevat veilige
aantallen en afwijscategorieën, geen BSSID, SSID, secret, pseudonieme netwerk-ID of coördinaten.

### 9.2 Alleen meten en verwerken

Als het dashboard nog niet moet starten:

```bash
./cyberbrein run --no-dashboard
```

Start het later met:

```bash
./cyberbrein dashboard
```

### 9.3 Eenmalige overrides

CLI-opties overschrijven de waarden uit `.env` voor één run. Voorbeeld:

```bash
./cyberbrein run --duration 120 --channels 36,40,44,48 --no-dashboard
```

Gebruik een handmatig meetronde-ID alleen wanneer de beheerprocedure dit vereist. Een ID is
maximaal 128 tekens, begint alfanumeriek en bevat alleen letters, cijfers, punten, underscores en
koppeltekens:

```bash
./cyberbrein run --round-id locatie-a-20260819 --no-dashboard
```

### 9.4 Wanneer is de run geslaagd?

Een succesvolle run eindigt met exitcode `0` en meldt geverifieerde opslag en geslaagde cleanup.
Bij gebruik zonder `--no-dashboard` blijft het proces actief zolang Streamlit draait. Stop het
dashboard met `Ctrl+C` nadat de bediening klaar is; dit verwijdert geen meetdata.

Controleer geaggregeerd, zonder inhoudelijke rijen te tonen:

```bash
psql -d cyberbrein_poc -v ON_ERROR_STOP=1 -c "
SELECT
  (SELECT count(*) FROM measurement_round) AS meetronden,
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

Verwacht één meetronde, minimaal één bruikbare netwerkvondst, precies drie scorefactoren per
netwerkvondst en `geldige_scores = t`.

## 10. Dashboard gebruiken

### 10.1 Starten en openen

Start als normale gebruiker:

```bash
./cyberbrein dashboard
```

Open op hetzelfde systeem:

```text
http://127.0.0.1:8501
```

Als de poort bezet is, kies een vrije lokale poort:

```bash
./cyberbrein dashboard --port 8502
```

### 10.2 Kaartoverzicht

Het overzicht toont:

- totaal aantal zichtbare netwerkvondsten;
- aantal vondsten met verhoogde aandacht;
- aantal vondsten met hoge aandacht;
- goedgekeurde meetzone(s);
- labelloze kaart met scorekleuren, clusters en spiderfy bij samenvallende punten;
- acties **Filters**, **Exporteer PDF** en **Meetdata verwijderen**.

De kaartpunten zijn indicatief. Behandel ze niet als bewezen access-pointlocaties.

### 10.3 Filters toepassen

1. Klik op **Filters**.
2. Kies desgewenst meetronde, band, encryptietype, scorekleur of signaalsterkte.
3. Open **Meer filters** voor zone en kanaal.
4. Klik op **Filters toepassen**.
5. Controleer de actieve-filtertelling in de filterknop en de gewijzigde KPI's en kaart.
6. Gebruik **Filters wissen** om de volledige meetronde te herstellen.

Wijzigingen in het formulier gelden pas na **Filters toepassen**. Een filterwijziging wist een
oude markerselectie en PDF-preview, zodat geen verouderde detail- of exportcontext zichtbaar blijft.

### 10.4 Detailweergave beoordelen

Selecteer een marker. Open bij een cluster eerst het cluster en vervolgens een uitgespreide
marker. De detailweergave toont:

- een verkorte en optioneel volledige pseudonieme netwerk-ID;
- totaalscore van 0 t/m 8 en aandachtkleur;
- drie scorefactoren: signaalsterkte, encryptietype en waarnemingsfrequentie;
- per factor de waargenomen waarde, categorie, punten, weging en uitleg;
- band, kanaal, frequentie, encryptietype, signaalsterkte, aantal waarnemingen en zone;
- de begrenzing dat de score geen volledig beveiligingsoordeel is.

Gebruik **Terug naar overzicht** om de detailweergave te sluiten.

## 11. PDF exporteren

Exporteer alleen de selectie die de ontvanger nodig heeft:

1. Pas eerst de gewenste filters toe en controleer de KPI's en kaart.
2. Klik op **Exporteer PDF**.
3. Wacht tot de preview is opgebouwd.
4. Controleer meetronde, filteromschrijving, tellingen, kaart en scorefactoren.
5. Klik op **Download PDF**.
6. Sla het bestand op in de afgesproken beveiligde locatie.
7. Verwijder onnodige lokale kopieën volgens de gegevenscyclus.

De PDF bevat de actieve filters, geaggregeerde tellingen, een labelloze kaart, netwerkvondsten en
uitlegbare scorefactoren. Hij bevat geen ruwe BSSID, ruwe SSID, secret of losse ruwe observaties.
De preview blijft alleen in Streamlit-sessiegeheugen; de server maakt geen permanent PDF-bestand.

Bij een ontbrekende kaartondergrond:

- controleer of CARTO-tegelservers bereikbaar zijn;
- probeer de preview opnieuw wanneer netwerktoegang is hersteld;
- controleer de rest van het rapport; een tegelprobleem verandert de opgeslagen meetdata niet.

## 12. Meetdata verwijderen na inzichtverstrekking

Deze procedure verwijdert de verwerkte meetronde uit PostgreSQL/PostGIS. Dit is een definitieve
hard delete en is niet hetzelfde als `discard`.

### 12.1 Voorwaarden

- De inzichten zijn verstrekt aan de afgesproken ontvanger.
- Een gewenste PDF is al gedownload en veilig opgeslagen.
- De geselecteerde meetronde en het ongefilterde aantal netwerkvondsten zijn gecontroleerd.
- De uitvoerder is bevoegd om definitief te verwijderen.

Het privacyveilige activiteitenlog staat standaard op:

```text
data/logs/operations.jsonl
```

Een alternatief lokaal pad kan vóór het starten van het dashboard worden ingesteld:

```bash
export CYBERBREIN_ACTIVITY_LOG_PATH="/afgesproken/pad/operations.jsonl"
./cyberbrein dashboard
```

Het log krijgt rechten `600` en bevat alleen UTC-tijd, actietype, status en geaggregeerde
verwijdertellingen. Het bevat geen meetronde-ID, netwerkidentifier of fouttekst.

### 12.2 Definitieve verwijderactie

1. Open het dashboard en verwijder eventuele filters om de volledige ronde te controleren.
2. Download zo nodig eerst de PDF.
3. Klik op **Meetdata verwijderen**.
4. Controleer de getoonde meetronde en het ongefilterde aantal netwerkvondsten.
5. Lees de waarschuwing.
6. Vink aan dat de inzichten zijn verstrekt en de meetdata permanent mag worden verwijderd.
7. Klik op **Bevestig verwijdering**.
8. Wacht op de succesmelding dat de ronde en de netwerkvondsten definitief zijn verwijderd.

De applicatie verwijdert de `measurement_round`. Door database-cascades verdwijnen ook gekoppelde
zones, netwerkvondsten, scores en scorefactoren. Operations voert daarna een aparte controle uit.
Alleen als alle tellingen nul zijn, wordt succes gemeld.

### 12.3 Verwijdering verifiëren

Het dashboard moet daarna melden dat geen verwerkte meetronde beschikbaar is. Voer aanvullend uit:

```bash
psql cyberbrein_poc -c "
SELECT
  (SELECT count(*) FROM measurement_round) AS meetronden,
  (SELECT count(*) FROM zone) AS zones,
  (SELECT count(*) FROM network_finding) AS netwerkvondsten,
  (SELECT count(*) FROM network_score) AS scores,
  (SELECT count(*) FROM score_factor) AS scorefactoren;
"
```

Verwacht uitsluitend nullen. Controleer daarna het activiteitenlog lokaal:

```bash
stat -c 'Logrechten: %a' data/logs/operations.jsonl
tail -n 1 data/logs/operations.jsonl
```

Verwacht rechten `600`, status `SUCCEEDED` en `verification_remaining` met waarde `0`. Kopieer het
log niet naar externe systemen zonder expliciete afspraak.

## 13. Herstel van een onderbroken of mislukte run

### 13.1 Beslisregel

Volg altijd de concrete instructie die de launcher na de fout toont. Verwijder bestanden niet
handmatig en voer de pipeline niet opnieuw uit als Storage al geverifieerd is.

| Situatie | Veilige actie |
|---|---|
| Fout vóór de eerste waarneming | De launcher ruimt de lege runtimebundel normaal automatisch op |
| Bruikbare buffer bewaard, Storage nog niet geverifieerd | Hervat met het getoonde `resume`-commando |
| Geldige maar onbruikbare buffer | Niet hervatten; verwijder expliciet met `discard` na controle |
| Storage geverifieerd, cleanup onvolledig | Niet opnieuw verwerken; bekijk resultaten en verwijder alleen resterende tijdelijke invoer met `discard` |
| Vorige verwerkte ronde aanwezig | Open dashboard; rond inzichtverstrekking en definitieve verwijdering af |
| Storage onbereikbaar | Herstel PostgreSQL of de URL en start daarna opnieuw |

### 13.2 Bewaarde ronde hervatten

Gebruik exact het meetronde-ID dat de launcher toont:

```bash
./cyberbrein resume <meetronde-id>
```

Of zonder dashboard:

```bash
./cyberbrein resume <meetronde-id> --no-dashboard
```

Een moderne bewaarde ronde bevat een private snapshot van zones en GPS-beleid. `resume` gebruikt
altijd die vastgezette waarden, ook als `.env` of het oorspronkelijke zonebestand intussen is
gewijzigd. Geef daarom geen `--zones`- of `--max-gps-accuracy`-override mee; deze wordt geweigerd.

### 13.3 Tijdelijke invoer definitief weggooien

Gebruik dit alleen voor de exact genoemde, niet meer te verwerken runtimebundel:

```bash
./cyberbrein discard <meetronde-id> --yes
```

`discard` verwijdert de tijdelijke SQLite-buffer, eventuele `-journal`, `-wal` en `-shm`-
sidecars, het secret, de zonesnapshot en het lifecycle-record. Het verwijdert geen verwerkte
PostGIS-meetdata. Het commando vereist `--yes` omdat herstel daarna niet mogelijk is.

## 14. Exitcodes en foutoplossing

| Exitcode | Betekenis | Actie |
|---|---|---|
| `0` | Handeling geslaagd | Voer de bijbehorende eindcontrole uit |
| `2` | Configuratie-, preflight-, privilege- of runtimebestandsfout | Lees veilige melding, herstel oorzaak, gebruik zo nodig `resume` of `discard` |
| `3` | Ingestion, Processing, Storage of opslagverificatie mislukt | Behoud invoer; herstel database/configuratie en hervat de getoonde ronde |
| `4` | Storage geverifieerd, cleanup onvolledig | Niet opnieuw verwerken; gebruik dashboard en ruim alleen tijdelijke invoer op |
| `5` | Geldige bron bevat binnen het vastgezette beleid geen bruikbare waarnemingen | Controleer ID en verwijder de ronde met het getoonde `discard`-commando |
| `127` | Vereist programma ontbreekt | Installeer of herstel het genoemde programma/de virtuele omgeving |
| `130` | Gebruiker heeft onderbroken | Volg de getoonde herstel- of cleanupinstructie |

### 14.1 Veelvoorkomende problemen

**Melding: start de launcher zonder sudo**

Voer `./cyberbrein run`, `resume`, `dashboard` en `discard` als normale gebruiker uit. Alleen
`setup-monitor` en `teardown-monitor` worden bewust met `sudo` gestart.

**Capture-interface ontbreekt of staat niet in monitor mode**

```bash
iw dev
iw dev wlan1 info
sudo ./cyberbrein setup-monitor --interface wlan1 --management-interface wlan0
```

Controleer USB-aansluiting, driver en systemd-service. Gebruik nooit blind een andere interface:
controleer eerst dat deze geen default route of SSH-sessie draagt.

**Geen 3D GPS-fix of nauwkeurigheid groter dan 15 meter**

Verplaats de ontvanger naar buiten met vrij zicht, controleer GPSD en wacht op een stabiele fix.
Verhoog de grens niet alleen om de controle te passeren; dat wijzigt het meetbeleid en de
kwaliteitseis.

```bash
systemctl status gpsd.socket --no-pager
gpspipe -w -n 10
```

**Storage bevat nog een verwerkte meetronde**

```bash
./cyberbrein dashboard
```

Rond de inzichtverstrekking af en volg paragraaf 12. Start daarna pas een nieuwe run.

**PostgreSQL/PostGIS kon niet veilig worden gecontroleerd**

```bash
systemctl status postgresql --no-pager
psql -d cyberbrein_poc -Atqc "SELECT current_database(), PostGIS_Version();"
```

Controleer `CYBERBREIN_DATABASE_URL`, peer-authenticatie, actieve service en PostGIS-extensie. De
workflow faalt gesloten en begint in deze situatie geen Collection.

**Zonebestand niet gevonden of ongeldig**

Controleer het pad in `.env`, bestandsrechten en de voorwaarden in paragraaf 7.5. Corrigeer geen
coördinaten zonder opnieuw akkoord op het meetgebied.

**Dashboard opent niet**

```bash
./cyberbrein dashboard --port 8502
```

Controleer terminalmelding, databasebereikbaarheid en of de gekozen poort vrij is. Een leeg
dashboard kan correct zijn als alle meetdata al is verwijderd.

**PDF-preview mist kaarttegels**

Controleer bereikbaarheid van de CARTO-tegelserver. De export bouwt verder zonder ondergrond als
tegels niet kunnen worden opgehaald; de meetdata blijft ongewijzigd.

**Verwijderactie meldt een fout**

Voer de actie niet herhaald uit zonder controle. Controleer eerst de vijf geaggregeerde tellingen
uit paragraaf 12.3 en de laatste lokale logregel. Een mislukte poging heeft status `FAILED` zonder
identifiers of fouttekst. Escaleer bij resterende records naar de systeembeheerder.

## 15. Beheer en onderhoud

### 15.1 Kwaliteitscontroles uitvoeren

Gebruik alleen de aparte `_test`-database:

```bash
export CYBERBREIN_TEST_DATABASE_URL="postgresql+psycopg2:///cyberbrein_test"
.venv/bin/ruff format --check src tests
.venv/bin/ruff check src tests
.venv/bin/pytest -q
.venv/bin/python -m pip check
```

Deze controles komen overeen met CI: formattering, linting en de testset. CI gebruikt Python 3.11
en een PostgreSQL 17/PostGIS 3.5-service. Voer tests nooit tegen `cyberbrein_poc` uit.

### 15.2 Monitor-mode-inrichting ongedaan maken

Geef de capture-adapter alleen op beheerdersbesluit terug aan NetworkManager:

```bash
sudo ./cyberbrein teardown-monitor --interface wlan1 \
  --management-interface wlan0
```

Controleer:

```bash
iw dev wlan1 info
nmcli device status
```

Verwacht `type managed`. De systemd-, NetworkManager- en udev-configuratie voor deze interface is
dan verwijderd. Dit verwijdert geen meetdata of projectbestanden.

### 15.3 Applicatie bijwerken

Werk alleen bij naar een door Cyberbrein goedgekeurde revisie en nooit tijdens een actieve of
bewaarde meetronde. Controleer vóór de update:

```bash
git status --short
psql -d cyberbrein_poc -Atqc "SELECT count(*) FROM measurement_round;"
find data/smoke data/local -maxdepth 1 -type f -printf '%f\n'
```

Als runtimebestanden aanwezig zijn, rond dan eerst herstel, inzichtverstrekking of verwijdering af.
Installeer na de goedgekeurde update opnieuw en voer de controles uit paragraaf 15.1 uit:

```bash
.venv/bin/pip install -e ".[dev]"
```

## 16. Handmatige onderliggende procedure voor diagnose

Gebruik de volgende procedure alleen wanneer de normale launcher niet kan worden gebruikt en een
technisch beheerder bewust de losse stappen moet diagnosticeren. De launcher blijft de aanbevolen
bediening omdat die lifecycle, snapshots en cleanup als één veiligheidsproces bewaakt.

### 16.1 Private invoer maken

```bash
ROUND_ID="diagnose-$(date -u +%Y%m%dT%H%M%SZ)"
SOURCE_DB="data/smoke/${ROUND_ID}.sqlite"
SECRET_PATH="data/local/${ROUND_ID}.secret"
umask 077
openssl rand -hex 32 > "$SECRET_PATH"
stat -c 'Secret-rechten: %a' "$SECRET_PATH"
```

Verwacht `600`. Toon het secret nooit en geef het niet als letterlijke CLI-argumentwaarde mee.

### 16.2 Collection

```bash
sudo -n /home/cyberbrein/poc/.venv/bin/python \
  -m cyberbrein.collection \
  --interface wlan1 \
  --database-path "$SOURCE_DB" \
  --measurement-round-id "$ROUND_ID" \
  --channels 36,40,44,48 \
  --duration 60 \
  --no-auto-monitor \
  --gpsd \
  --require-gps-fix \
  --max-gps-accuracy 15
```

Ga alleen verder bij exitcode `0` en een bruikbaar aantal waarnemingen.

### 16.3 Pipeline

Voer de pipeline als normale gebruiker uit:

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

Controleer na succes dat bron en secret weg zijn:

```bash
test ! -e "$SOURCE_DB" && echo "Bronbuffer verwijderd"
test ! -e "$SECRET_PATH" && echo "Secret verwijderd"
```

Bij een fout blijven buffer en secret voor herstel staan. Gebruik niet alsnog willekeurige
handmatige verwijdercommando's; bepaal eerst aan de hand van de exitcode of Storage al is
geverifieerd.

## 17. Operationele eindchecklist

### Na een succesvolle meetronde

- [ ] De pipeline heeft exitcode `0` gemeld.
- [ ] PostgreSQL/PostGIS bevat precies één meetronde.
- [ ] Er zijn bruikbare netwerkvondsten en precies drie factoren per vondst.
- [ ] Alle scores liggen tussen 0 en 8 en hebben de juiste kleurklasse.
- [ ] Tijdelijke buffer, sidecars, secret, zonesnapshot en lifecycle-record zijn verwijderd.
- [ ] Dashboard en detailweergave zijn gecontroleerd.
- [ ] Eventuele PDF is met de juiste filters gedownload naar een goedgekeurde locatie.

### Na inzichtverstrekking en verwijdering

- [ ] Het dashboard meldt dat geen verwerkte meetronde beschikbaar is.
- [ ] Alle vijf PostGIS-tellingen zijn nul.
- [ ] De laatste Operations-logregel heeft status `SUCCEEDED`.
- [ ] `verification_remaining` is `0`.
- [ ] Het activiteitenlog heeft rechten `600`.
- [ ] Eventuele gedownloade PDF-kopieën vallen onder een bekende eigenaar en bewaartermijn.
- [ ] Er zijn geen achtergebleven tijdelijke runtimebestanden.

## 18. Escalatiegegevens

Leg vóór operationele overdracht de volgende organisatiegegevens vast in de beheerde versie van
dit runbook:

| Onderwerp | In te vullen door Cyberbrein |
|---|---|
| Functioneel eigenaar | Naam en contactroute |
| Technisch beheerder | Naam en contactroute |
| Privacy-/securitycontact | Naam en contactroute |
| Goedgekeurde projectrevisie | Git-commit of release |
| Goedgekeurde Linux-image | Naam en versie |
| Fysieke projectlocatie | Systeem-/assetnummer |
| Bewaartermijn PDF-export | Termijn en verantwoordelijke |
| Incident- en escalatieprocedure | Interne referentie |

Escaleer direct bij vermoeden van ongeautoriseerde meting, verlies van een apparaat, onverwachte
ruwe identifiers in uitvoer, een niet-verifieerbare verwijdering of meetdata buiten de afgesproken
opslaglocaties. Stop in dat geval de workflow, maar verwijder geen bewijsmateriaal of bestanden
zonder instructie van de verantwoordelijke.

## Bijlage A. Beknopte normale werkinstructie

```bash
cd /home/cyberbrein/poc

# Eenmalig na installatie:
sudo ./cyberbrein setup-monitor --interface wlan1 --management-interface wlan0

# Per meetronde, als normale gebruiker:
./cyberbrein run

# Dashboard later opnieuw openen:
./cyberbrein dashboard

# Alleen bij een door de launcher als herstelbaar gemelde ronde:
./cyberbrein resume <meetronde-id>

# Alleen voor expliciet te verwijderen tijdelijke invoer:
./cyberbrein discard <meetronde-id> --yes
```

Verwijder verwerkte PostGIS-meetdata uitsluitend via **Meetdata verwijderen** in het dashboard,
na inzichtverstrekking en expliciete bevestiging.

## Bijlage B. Documenthistorie

| Versie | Datum | Wijziging | Auteur/reviewer |
|---|---|---|---|
| 1.0 | 19 augustus 2026 | Samengevoegd operationeel runbook op basis van de actuele PoC, runtimecontracten en fase-runbooks | In te vullen |

## Bijlage C. Conversie naar DOCX

Maak bij voorkeur eerst een kopie van de Markdown-bron en converteer met Pandoc. De optie `--toc`
maakt in DOCX een inhoudsopgaveveld; open het bestand in Word of LibreOffice en werk de
inhoudsopgave bij zodat paginanummers definitief worden berekend.

```bash
pandoc docs/runbook.md \
  --from=gfm \
  --to=docx \
  --toc \
  --metadata title="Runbook Cyberbrein Wi-Fi Exposure PoC" \
  --output=runbook-cyberbrein-wifi-exposure-poc.docx
```

Gebruik voor de definitieve huisstijl desgewenst een door Cyberbrein beheerd referentiedocument:

```bash
pandoc docs/runbook.md \
  --from=gfm \
  --to=docx \
  --toc \
  --reference-doc=cyberbrein-reference.docx \
  --output=runbook-cyberbrein-wifi-exposure-poc.docx
```

Controleer na conversie minimaal de tabellen, codeblokken, selectievakjes, inhoudsopgave,
paginawissels en kop-/voetteksten. De Markdown-bron blijft de onderhoudbare basisversie.
