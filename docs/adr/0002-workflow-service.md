# ADR-0002: CLI-vrije workflowcoördinatie

- Status: Geaccepteerd
- Datum: 2026-08-06

## Context

De launcher combineert argumentparsing, omgevingsconfiguratie, privilegecontrole, preflight,
runtimebestanden, subprocessen, herstelbeslissingen en Nederlandstalige uitvoer in één module. De
unit-tests moeten daardoor module-globals en `subprocess.run` patchen. Een toekomstige tweede
presentatie-adapter kan deze orchestratielogica niet veilig hergebruiken.

## Besluit

De launcher wordt een package met een dunne CLI-adapter en een `WorkflowService`. De service
ontvangt requests, voert de vaste volgorde uit en retourneert een gestructureerde outcome. De CLI
blijft eigenaar van argparse, omgevingsdefaults, privilegecontrole en gebruikersmeldingen.

Er worden alleen seams toegevoegd die nu testbaarheid opleveren: één command-runner en callables
voor GPS- en monitorpreflight. Er komt geen dependency-injectioncontainer en geen afzonderlijke
Protocol-klasse voor ieder hulpfunctietje.

## Alternatieven

- Alleen hulpfuncties over meerdere modules verdelen is afgewezen omdat globale patches en
  presentatiegekoppelde control flow dan blijven bestaan.
- Een volledige hexagonale laag met een groot aantal ports is afgewezen als disproportioneel voor
  één lokale Pi en één productie-implementatie per runtimefunctie.
- De bestaande module ongewijzigd laten is afgewezen omdat lifecycle- en herstelgedrag verder moet
  groeien voordat een GUI kan worden overwogen.

## Gevolgen

CLI en toekomstige presentatie kunnen dezelfde applicatieservice gebruiken. De extra package- en
request/outcome-typen vergroten de structuur, maar maken orchestratietests onafhankelijk van
argparse en console-uitvoer.
De gerealiseerde service gebruikt één command-runner, twee preflight-callables en één kleine
event-callback voor de bestaande directe startmelding. Orchestratietests gebruiken deze seams
zonder module-globals te patchen.
