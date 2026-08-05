# Cyberbrein Exposure PoC

Proof of concept voor het verzamelen, verwerken en visualiseren van passieve Wi-Fi-meetdata.

## Onderdelen

- Collection: passieve Wi-Fi-metadata verzamelen
- Ingestion: valideren en pseudonimiseren
- Processing: deduplicatie, GPS-controle, zonekoppeling en scoreberekening
- Storage: PostgreSQL/PostGIS-opslag van verwerkte meetrondegegevens
- Presentation: lokaal Streamlit GIS-dashboard en PDF-export
- Operations: CI, logging, runbook en opschoning

De operationele fase-3-keten wordt gestart met `python -m cyberbrein.pipeline`. Zie
[`docs/phase-03-runtime-runbook.md`](docs/phase-03-runtime-runbook.md) voor veilige invoer,
uitvoering en opschoning.

SQLite wordt uitsluitend gebruikt als tijdelijke Collection-buffer. De normale opslag voor
Processing, Presentation en rapportage is PostgreSQL/PostGIS.

Voor normaal gebruik hoeft de volledige keten maar één keer geconfigureerd te worden:

```bash
cp .env.example .env
# Pas in .env minimaal CYBERBREIN_INTERFACE aan en plaats data/local/zones.geojson.
sudo ./cyberbrein setup-monitor --interface wlan1
./cyberbrein run
```

Start dit commando zonder `sudo`; de launcher vraagt alleen voor de Collection-stap om het
sudo-wachtwoord.

De eenmalige setup houdt `wlan0` beschikbaar voor netwerktoegang of een access point en maakt
alleen de geconfigureerde externe adapter persistent unmanaged/in monitor mode. Ongedaan maken kan
met `sudo ./cyberbrein teardown-monitor --interface wlan1`.

Dit maakt automatisch een meetronde-ID en mode-600-secret, voert Collection en Pipeline uit,
verwijdert de tijdelijke buffer en het secret uitsluitend na geverifieerde opslag, en start daarna
het lokale dashboard. Alleen het dashboard opnieuw starten kan met `./cyberbrein dashboard`.
Gebruik `./cyberbrein run --no-dashboard` wanneer alleen verzamelen en verwerken gewenst is.
Na een onderbreking kan een door de launcher bewaarde meetronde worden hervat met het getoonde
`./cyberbrein resume <meetronde-id>`-commando. Een geldige maar onbruikbare buffer wordt niet als
hervatbaar gepresenteerd; verwijder die expliciet met het getoonde
`./cyberbrein discard <meetronde-id> --yes`-commando.

Zie [`docs/phase-03-runtime-runbook.md`](docs/phase-03-runtime-runbook.md) voor configuratie,
veilig herstel en de afzonderlijke onderliggende commando's. Zie
[`docs/phase-04-presentation-runbook.md`](docs/phase-04-presentation-runbook.md) voor gebruik,
PDF-export en veilige controles.
