# Fase 4: acceptatieresultaten

## Geautomatiseerde controles

- Ruff-format en Ruff-lint zijn groen.
- Alle 188 unit-, integratie- en privacytests slagen.
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

De Streamlit-testharness voerde daarnaast het script zonder applicatiefouten uit en toonde de
lege-datamelding plus drie kerncijfers met waarde nul. Deze dataset valideert de
lege-kaartafhandeling.

## Functionele dashboardacceptatie

Voor de functionele dashboardacceptatie is dezelfde buffer opnieuw verwerkt met een expliciete,
tijdelijke GPS-nauwkeurigheidsgrens van 35 meter. De standaardgrens in de applicatie is niet
gewijzigd en blijft 15 meter. Ingestion en Processing accepteerden alle 1265 waarnemingen. Storage
bevatte daarna 18 netwerkvondsten, 18 scores en 54 scorefactoren: precies de drie vastgelegde
factoren per netwerkvondst. De scoreverdeling was 6 groen, 12 geel en 0 rood.

Het dashboard is voor de handmatige acceptatietest tijdelijk op `0.0.0.0:8501` gestart en vanaf een
mobiele telefoon bediend. De volgende onderdelen werkten zoals bedoeld:

- de kaart toont wegen en terreinvormen zonder straatnamen of bedrijfslabels;
- samenvallende netwerkvondsten worden geclusterd en na selectie uitgespreid;
- een uitgespreide netwerkvondst opent de detailweergave met pseudonieme netwerk-ID, technische
  metadata en precies drie scorefactoren;
- de PDF-preview opent zonder applicatiefout en gebruikt dezelfde labelloze kaartstijl als het
  dashboard;
- ruwe BSSID's, exacte SSID's en exacte access-pointlocaties worden niet getoond.

De externe kaarttegels ontvangen alleen de opgevraagde kaartuitsnede en het IP-adres van de
dashboardserver. Pseudonieme netwerk-ID's, scores en waarnemingsmetadata worden niet naar de
tegelprovider gestuurd.

## Open acceptatiepunt

De functionele werking met gekleurde netwerkvondsten is handmatig aangetoond, maar definitieve
acceptatie van de GPS-kwaliteit vereist nog een nieuwe buitenmeting waarbij
`gps_accuracy_m <= 15` geldt. De twee bestaande hardwarebuffers voldoen daar niet aan: de
67-regelige GPS-buffer bevat nauwkeurigheden van 20,52 tot 24,13 meter en de 1265-regelige buffer
bevat geen waarnemingen binnen 15 meter. De tijdelijke 35-meterverwerking is daarom uitsluitend
functioneel testbewijs en geen bewijs voor NFR-03.
