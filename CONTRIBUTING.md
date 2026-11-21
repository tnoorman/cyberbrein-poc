# Contributing to Cyberbrein Exposure PoC

Thank you for your interest in making cybersecurity awareness more accessible\. Cyberbrein Exposure PoC is an early\-stage, privacy\-conscious research project developed for Stichting Cyberbrein\.

Contributions are welcome, particularly when they help people understand digital exposure without increasing privacy risk\.

## Where to start

Good first contributions include:

- Clarifying English or Dutch documentation and adding diagrams\.
- Improving automated tests, fixtures, error messages, and reproducibility\.
- Building **synthetic** example data and a no\-hardware demonstration path\.
- Improving the accessibility and clarity of GIS dashboards and reports\.
- Reviewing privacy boundaries, data\-retention behavior, and dependency security\.

For larger features or architectural changes, please open an issue to discuss your proposal before implementation\. The project has explicit subsystem boundaries and lifecycle safety invariants that should not be changed accidentally\.

## Local development

This project requires Python 3\.11\+ and uses a `src/` package layout\.

```bash
git clone https://github.com/tnoorman/cyberbrein-poc.git
cd cyberbrein-poc
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

For integration tests, configure a separate PostgreSQL/PostGIS database\. The test database name must end with `_test` and must never contain real measurement data\. The repository’s [CI workflow](.github/workflows/ci.yml) shows an example using `CYBERBREIN_TEST_DATABASE_URL`\.

Before submitting a pull request, run:

```bash
ruff format --check src tests
ruff check src tests
pytest -q
```

If your environment cannot run the integration suite, explain which checks you ran and why the rest were not run\. Never point tests at a live or non\-test database\.

## Project boundaries

The architecture follows this flow:

```text
Collection -> Ingestion -> Processing -> Storage -> Presentation
```

Operations owns deletion and data lifecycle; Workflow coordinates execution and recovery\. Read [architecture boundaries](docs/architecture-boundaries.md) and [runtime contract](docs/runtime-contract.md) before modifying the pipeline\.

In particular:

- Collection must remain passive and within approved scope\. Do not add network joining, payload interception, or tracking of clients\.
- Keep raw network identifiers and secrets out of downstream storage, output, logs, tests, and sample datasets\.
- Do not weaken pseudonymization, zone boundaries, GPS\-quality safeguards, or verified deletion/recovery behavior\.
- Do not portray a geospatial finding as the confirmed location of an access point, or an exposure score as a verified vulnerability\.
- Preserve explicit boundaries between subsystems and provide tests for behavior changes\.

## Privacy and safe examples

**Never include real\-world measurements or sensitive operational information in a public contribution\.** This includes real BSSIDs, SSIDs, client addresses, raw capture files, precise GPS traces, site identities, secrets, credentials, or identifiable screenshots and PDFs\.

Use invented identifiers, synthetic datasets, and generalized locations\. If you discover that a public artifact contains potentially sensitive information, do not amplify it in a public issue\.

## Pull request process

1. Create a focused branch and make a small, reviewable change\.
2. Explain the problem, your proposed solution, and any limitations\.
3. Add or update tests when changing code behavior\.
4. Update documentation when changing runtime behavior, configuration, user\-visible messages, or privacy assumptions\.
5. Run formatting, linting, and tests, and report the results in your pull request\.
6. Describe any privacy, security, or deployment implications so maintainers can review them deliberately\.

Suggested pull request checklist:

```markdown
- [ ] I followed the architecture and privacy boundaries.
- [ ] I added or updated relevant tests and documentation.
- [ ] I ran Ruff and applicable tests, or explained why I could not.
- [ ] My change contains no real measurement data, secrets, or identifying information.
- [ ] I described user-facing or operational changes and any known limitations.
```

## Reporting security vulnerabilities

Please **do not disclose an exploitable vulnerability or sensitive data in a public GitHub issue**\. Contact the project maintainer privately using an agreed channel to coordinate responsible disclosure\. If no private channel is available, open only a generic request to establish a secure contact method, without revealing technical details\.

## Licensing

This repository is distributed under the [Apache License 2\.0](LICENSE)\. By submitting a contribution, you agree to provide it under the project’s license and confirm you have the right to do so\. Preserve required attribution and third\-party license notices\.
