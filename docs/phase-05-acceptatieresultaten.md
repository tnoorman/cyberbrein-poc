# Fase 5: acceptatieresultaten

## Geautomatiseerde controles

- Storage verwijdert de root-meetronde en alle gekoppelde records via foreign-key-cascades.
- Een afzonderlijke controlequery bevestigt nul records in `measurement_round`, `zone`,
  `network_finding`, `network_score` en `score_factor`.
- Een onbekende meetronde wordt niet als succesvolle verwijdering gerapporteerd.
- Na verwijdering kan een nieuwe meetronde worden opgeslagen.
- De Operations-integratietest bevestigt dat Presentation na verwijdering geen actieve meetronde
  meer vindt.
- Het activiteitenlog krijgt rechten `600` en bevat geen meetronde-ID of fouttekst.
- De Streamlit-test bevestigt dat expliciete toestemming verplicht is, de verwijdering daarna wordt
  uitgevoerd en de lege-datamelding verschijnt.
- Ruff-format en Ruff-lint zijn groen; alle 195 tests slagen.

## Privacy- en opslaggrenzen

De verwijderactie logt uitsluitend tijd, uitkomst en geaggregeerde tellingen. De server maakt voor
PDF-export geen permanent bestand; de preview staat alleen in Streamlit-sessiegeheugen en wordt na
verwijdering gewist. Een reeds gedownloade PDF valt buiten de serveropslag en blijft onder beheer
van de gebruiker.

## Handmatig acceptatiepunt

De bestaande functionele runtime-meetronde is tijdens implementatie niet verwijderd. Daardoor
blijft zij beschikbaar voor de visuele fase-6-acceptatie. De definitieve AT-06-test wordt na de
nieuwe buitenmeting uitgevoerd: eerst dashboard en PDF beoordelen, daarna bewust verwijderen en de
controlequery plus het activiteitenlog controleren.
