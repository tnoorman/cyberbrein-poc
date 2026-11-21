# Cyberbrein Exposure PoC

**Making digital exposure visible, understandable, and actionable\.**

Cyberbrein Exposure PoC is an open\-source, privacy\-conscious cybersecurity awareness project developed for **Stichting Cyberbrein**, a Dutch nonprofit focused on cyber resilience\. It explores what organizations can learn from limited, passive Wi\-Fi metadata collected in authorized areas, such as business parks, and translates the resulting observations into understandable geographic insights\.

The project began as a Software Engineering graduation project and is now being developed toward a reusable awareness and educational tool\.

> **Project status:** Proof of concept (v0.1.0). This is a research and awareness tool, not a production-ready monitoring platform, vulnerability scanner, security certification, or proof of the physical location of a wireless access point.

## Why it exists

Cybersecurity risks are often invisible to people who are responsible for managing them\. Smaller businesses and local organizations may not have dedicated security teams or the resources to turn technical observations into practical conversations about cyber resilience\.

Cyberbrein Exposure PoC addresses that gap by demonstrating how *carefully scoped* wireless metadata can be transformed into aggregate, interpretable findings\. Its focus is **awareness and education**, not identifying individuals, accessing networks, or attributing devices to specific businesses\.

## What the proof of concept does

- **Passive collection:** observes selected metadata from Wi\-Fi beacon and probe\-response frames\. It does not join wireless networks or inspect payloads\.
- **Privacy\-focused ingestion:** validates incoming data, pseudonymizes BSSIDs with a measurement\-round secret, and reduces SSIDs to a presence indicator before downstream processing\.
- **Processing and scoring:** performs deduplication, GPS\-quality checks, approved\-zone assignment, aggregation, and interpretable exposure scoring\.
- **Geospatial storage:** stores processed measurement rounds and findings in PostgreSQL/PostGIS; temporary raw collection buffers use SQLite\.
- **Local presentation:** provides a Streamlit GIS dashboard, filters, explanatory score factors, and PDF export\.
- **Controlled lifecycle:** supports validation, recovery of interrupted rounds, verified storage, and explicit deletion workflows\.

## Architecture

```text
Authorized measurement area
            |
            v
  Collection (temporary SQLite)
            |
            v
  Ingestion (validation + pseudonymization)
            |
            v
  Processing (GPS + zones + scores)
            |
            v
  Storage (PostgreSQL / PostGIS)
            |
            v
  Presentation (local GIS dashboard + PDF)

  Operations manages retention and deletion.
  Workflow coordinates collection and processing.
```

The pipeline keeps raw network identifiers out of downstream storage and visualizations\. Its scores are **awareness indicators**, not statements that a particular network is compromised or insecure\.

For implementation details, see the [architecture and privacy boundaries](docs/architecture-boundaries.md) and [runtime contract](docs/runtime-contract.md)\.

## Privacy and responsible use

Only collect data in an area and under conditions for which you have appropriate authorization and an approved privacy plan\. Wireless metadata can still be sensitive even when no network connection is made\.

The current design includes several safeguards:

- No connection to observed Wi\-Fi networks and no payload inspection\.
- No collection of client addresses or IP addresses in the collection subsystem\.
- No raw BSSIDs, SSIDs, or round secrets in downstream PostGIS records or dashboard output\.
- Measurement\-round\-specific pseudonymization, approved geographic zones, and GPS\-quality checks\.
- Private temporary runtime files, verified cleanup, and an explicit post\-reporting deletion operation\.
- A dashboard bound to localhost by default, rather than a public service\.

**Important limitations:** Pseudonymization is not equivalent to anonymization\. A map marker is an indicative measurement or aggregation result, not the verified physical location of an access point\. The map tile provider can receive the requesting server’s IP address and visible map extent, but not network identifiers or measured observations\. Review local law, privacy obligations, and organizational policies before any fieldwork\.

Do **not** submit real measurements, identifiers, secrets, GPS traces, or identifiable site information to this public repository\.

## Requirements

This proof of concept was designed for a Linux\-based measurement environment with:

- Python **3\.11\+**\.
- PostgreSQL with the PostGIS extension &#40;the project runbooks describe PostgreSQL 17 and PostGIS 3\.5&#41;\.
- A compatible, dedicated Wi\-Fi adapter supporting monitor mode, plus a separate management interface\.
- GPSD and an appropriate GPS receiver for real\-world measurements\.
- A locally approved GeoJSON zone file and the configuration required by the runtime runbooks\.

These are project\-specific operational requirements, not a claim that every operating system, adapter, or deployment is supported\.

## Getting started

### 1\. Install the Python project

```bash
git clone https://github.com/tnoorman/cyberbrein-poc.git
cd cyberbrein-poc
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

### 2\. Prepare the local environment

Follow the [PostgreSQL/PostGIS and presentation runbook](docs/phase-04-presentation-runbook.md) and the [runtime runbook](docs/phase-03-runtime-runbook.md)\. Configure at least `CYBERBREIN_INTERFACE` in `.env`, and supply a locally approved zone file at the configured `CYBERBREIN_ZONES` path &#40;default: `data/local/zones.geojson`&#41;\.

The supplied `.env.example` assumes a local PostgreSQL Unix\-socket connection with peer authentication\. Adjust it for your own approved setup\. Never commit `.env`, secrets, or real measurement data\.

### 3\. Run an authorized measurement

**Caution:** Monitor\-mode setup changes the configuration of the specified wireless adapter and can persist across restarts\. Read the runbook first, check interface names, and do not run these commands on a network you are not authorized to assess\.

```bash
# Replace wlan1 with your approved dedicated capture adapter.
sudo ./cyberbrein setup-monitor --interface wlan1

# Run the launcher as a normal user, not with sudo.
./cyberbrein run
```

The launcher elevates only the collection step when needed\. To process without starting the dashboard, use `./cyberbrein run --no-dashboard`\. To reopen the dashboard for an existing processed round, use `./cyberbrein dashboard`\.

A completed round remains available for review until it is explicitly removed through the Operations flow in the dashboard\. The workflow does not silently overwrite or delete existing processed findings\. Interrupted rounds may require the documented `resume` or `discard` procedures; do not manually remove runtime files without reviewing the [runtime runbook](docs/phase-03-runtime-runbook.md)\.

When the adapter is no longer needed in persistent monitor mode:

```bash
sudo ./cyberbrein teardown-monitor --interface wlan1
```

## Development and tests

```bash
ruff format --check src tests
ruff check src tests
pytest -q
```

Integration tests require a **separate PostGIS test database**\. The tests reject database names that do not end in `_test`\. See the [CI workflow](.github/workflows/ci.yml) for an example of the test database setup\. Project documentation records a 286\-test local acceptance run during the graduation phase; this is a historical verification result, not a claim about every later commit or environment\.

## Roadmap

The next development priorities are proposals, not released capabilities:

1. **Reproducible demonstrations:** privacy\-safe synthetic or simulated datasets and a guided demo that does not require live collection\.
2. **Developer onboarding:** clearer installation, fixtures, diagrams, contributor guidance, and repeatable test environments\.
3. **Robustness and security:** strengthen error handling, automated regression tests, dependency maintenance, and security review\.
4. **Accessibility and communication:** improve dashboard explanations, usability, accessible reporting, and awareness materials for nontechnical audiences\.
5. **Responsible pilot readiness:** refine deployment guidance, governance, privacy review, and validation with willing partner organizations before wider use\.

A major goal is to make the software easier for other maintainers and organizations to evaluate, contribute to, and adapt responsibly\.

## Contributing

Contributions are welcome, especially improvements to tests, documentation, accessibility, privacy safeguards, and reproducible demos\. Please read [CONTRIBUTING\.md](CONTRIBUTING.md) before opening a pull request\.

For security\-sensitive findings, **do not post exploit details, real captures, or private data in a public issue**\. Arrange a private reporting channel with the maintainer first\.

## Background and acknowledgments

This project was created as an HBO\-ICT Software Engineering graduation project and developed for **Stichting Cyberbrein**\. The longer\-term ambition is to support cyber\-resilience awareness in business parks and other local organizational settings\.

It is currently an early\-stage open\-source project\. Interest from potential stakeholders should not be confused with confirmed deployment, adoption, endorsement, or formal partnership\.

## License

Licensed under the **Apache License, Version 2\.0**\. See [LICENSE](LICENSE)\.
