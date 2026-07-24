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

Het dashboard wordt lokaal gestart met:

```bash
export CYBERBREIN_DATABASE_URL="postgresql+psycopg2:///cyberbrein_poc"
.venv/bin/streamlit run src/cyberbrein/presentation/app.py \
  --server.address 127.0.0.1 \
  --server.headless true
```

Zie [`docs/phase-04-presentation-runbook.md`](docs/phase-04-presentation-runbook.md) voor
database-inrichting, gebruik, PDF-export en veilige controles.
