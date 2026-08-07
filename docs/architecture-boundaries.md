# Architectuur- en privacygrenzen

Dit document legt de technische grenzen vast voor de implementatie van de meetpipeline. Elk
subsysteem verwerkt alleen de gegevens en verantwoordelijkheden die hieronder zijn beschreven.

## Datastroom

De datastroom loopt in één richting:

```text
Collection -> Ingestion -> Processing -> Storage -> Presentation
```

Operations beheert de levenscyclus van de gegevens rondom deze datastroom, maar vormt geen extra
verwerkingsstap in de pipeline.

## Collection

Collection:

- ontvangt alleen passieve metadata uit beacon- en probe-responseframes;
- verbindt niet met netwerken;
- inspecteert geen payload;
- schrijft tijdelijke ruwe brondata naar SQLite;
- bewaart geen IP-adressen of clientadressen.

Collection verzamelt uitsluitend de brongegevens die nodig zijn voor het afgesproken
invoercontract van Ingestion.

## Ingestion

Ingestion:

- selecteert alleen velden uit het afgesproken invoercontract;
- valideert verplichte velden en basisbereiken;
- pseudonimiseert de BSSID met een meetrondegebonden secret;
- zet de SSID om naar de indicator `ssid_present`;
- geeft geen ruwe BSSID of SSID door aan volgende subsystemen.

Het meetrondegebonden secret blijft binnen de ingestiongrens en wordt niet onderdeel van de
doorgegeven waarneming.

## Processing

Processing:

- werkt alleen met geaccepteerde en gepseudonimiseerde waarnemingen;
- filtert waarnemingen op GPS-kwaliteit;
- koppelt waarnemingen uitsluitend aan goedgekeurde zones;
- aggregeert netwerkvondsten;
- berekent uitlegbare scorefactoren.

Processing krijgt geen toegang tot ruwe BSSID's, SSID's of tijdelijke brondata.

## Storage

Storage:

- bevat geen ruwe observaties;
- bevat geen secret;
- bevat alleen de benodigde gegevens over meetronde, zone, netwerkvondst, score en scorefactor.

Storage ontvangt uitsluitend verwerkte resultaten van Processing.

## Presentation

Presentation:

- leest alleen uit Storage;
- presenteert een marker niet als bewezen locatie van een access point;
- toont geen ruwe BSSID of SSID.

De presentatie maakt duidelijk dat een marker een meet- of aggregatieresultaat weergeeft en geen
bewijs van de fysieke locatie van een netwerkapparaat.

## Operations

Operations:

- verwijdert tijdelijke SQLite-brondata pas nadat de verwerking succesvol is afgerond;
- verwijdert na de inzichtverstrekking alle gegevens van de meetronde;
- controleert en registreert dat de verwijdering is voltooid.

Een mislukte verwerking of mislukte verwijderingscontrole wordt expliciet gerapporteerd en mag
niet als succesvolle afronding worden behandeld.

## Afhankelijkheidsregels

- Presentation importeert Collection en Ingestion niet.
- Processing importeert Presentation niet.
- Storage importeert Presentation niet.
- Shared bevat alleen domeintypen of fouten die aantoonbaar door meerdere subsystemen worden
  gedeeld.
- Er komt geen generieke `utils.py`; gedeelde code krijgt een concrete domeinverantwoordelijkheid
  en een bijpassende naam.

Deze regels gelden voor zowel directe als indirecte afhankelijkheden. Gegevensuitwisseling tussen
subsystemen verloopt via expliciete contracten en niet via interne implementatiedetails van een
ander subsysteem.

## Runtime en Workflow

Workflow is de applicatiecoördinatielaag boven Collection en Pipeline:

- `workflow.cli` is de presentatie-adapter voor argumenten, privileges, omgevingsdefaults en
  Nederlandstalige gebruikersmeldingen;
- `WorkflowService` bepaalt de volgorde, subprocessgrenzen en herstelbeslissingen en bevat geen
  argparse- of consolelogica;
- Workflow gebruikt gepubliceerde Pipeline-exitcodes en cleanupcontracten en leest niet direct de
  interne SQLite-tabellen van Collection;
- Collection blijft eigenaar van inspectie van de ruwe bronbuffer;
- actieve rondes zetten zones en maximale GPS-nauwkeurigheid vast in private runtimeartefacten;
- lifecycletransities worden door `RoundStateStore` gecontroleerd; ontbrekende metadata is alleen
  legacy wanneer zowel record als zonesnapshot ontbreken;
- een corrupt record, een losse snapshot of een digestverschil leidt tot een gesloten fout en
  nooit tot automatisch ruimer beleid;
- alleen `PREPARED` en `COLLECTED` zijn hervatbaar. `UNUSABLE` en `STORED_UNCLEANED` vereisen
  expliciet discard.

Een toekomstige GUI is een tweede presentatie-adapter en mag deze regels niet dupliceren. Een
progress-port, proceslocking of privilege-helper wordt pas toegevoegd wanneer die tweede actor
daadwerkelijk wordt geïmplementeerd.
