# Fase 4: acceptatieresultaten

## Geautomatiseerde controles

- Ruff-format en Ruff-lint zijn groen.
- Alle 184 unit-, integratie- en privacytests slagen.
- De integratietests gebruiken echte PostgreSQL/PostGIS-opslag.
- Integratietests gebruiken de afzonderlijke database `cyberbrein_test` en weigeren een
  databasenaam zonder `_test`-suffix; de runtime-database wordt niet door test-cleanup geraakt.
- Geometrytypen, SRID 4326, GiST-indexen, atomaire vervanging en de één-actieve-ronde-regel zijn
  gecontroleerd.
- De PDF-tests controleren actieve filters, score-uitleg, privacygrenzen en generatie binnen tien
  seconden.

## Lokale systeemrooktest

De lokale PostgreSQL 17/PostGIS 3.5-database is via peer-authenticatie bereikbaar. De pipeline
heeft een afgeschermde werkkopie van een bestaande Collection-buffer met 1265 waarnemingen
verwerkt. Ingestion accepteerde alle regels. Processing wees alle 1265 regels veilig af omdat hun
GPS-nauwkeurigheid boven de definitieve verslaggrens van 15 meter lag.

Storage heeft daarop correct één afgeronde meetronde en de goedgekeurde zone opgeslagen, met nul
netwerkvondsten en nul scorefactoren. De tijdelijke bronkopie en het tijdelijke secret zijn pas na
opslagverificatie verwijderd; de oorspronkelijke Collection-buffer bleef intact.

Het Streamlit-dashboard is uitsluitend op `127.0.0.1:8501` gestart. De healthcontrole antwoordde
`ok`, waarna het proces gecontroleerd is gestopt. De Streamlit-testharness voerde daarnaast het
script zonder applicatiefouten uit en toonde de lege-datamelding plus drie kerncijfers met waarde
nul. Deze dataset valideert de lege-kaartafhandeling.

## Open acceptatiepunt

Een inhoudelijke hardwaretest met gekleurde netwerkvondsten vereist een nieuwe buitenmeting waarbij
`gps_accuracy_m <= 15` geldt. De twee bestaande hardwarebuffers voldoen daar niet aan: de
67-regelige GPS-buffer bevat nauwkeurigheden van 20,52 tot 24,13 meter en de 1265-regelige buffer
bevat geen waarnemingen binnen 15 meter. De geautomatiseerde tests dekken intussen een gevulde
meetzone met groene en gele vondsten, gecombineerde filters, detailweergave en PDF-export.
