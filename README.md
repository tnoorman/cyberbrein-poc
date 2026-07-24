# Cyberbrein Exposure PoC

Proof of concept voor het verzamelen, verwerken en visualiseren van passieve Wi-Fi-meetdata.

## Onderdelen

- Collection: passieve Wi-Fi-metadata verzamelen
- Ingestion: valideren en pseudonimiseren
- Processing: deduplicatie, GPS-controle, zonekoppeling en scoreberekening
- Storage: opslag van meetrondegegevens
- Presentation: dashboard en export
- Operations: CI, logging, runbook en opschoning

De operationele fase-3-keten wordt gestart met `python -m cyberbrein.pipeline`. Zie
[`docs/phase-03-runtime-runbook.md`](docs/phase-03-runtime-runbook.md) voor veilige invoer,
uitvoering en opschoning.
