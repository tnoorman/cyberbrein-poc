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
- Ruff-format en Ruff-lint zijn groen; de actuele volledige suite van 202 tests slaagt.

## Privacy- en opslaggrenzen

De verwijderactie logt uitsluitend tijd, uitkomst en geaggregeerde tellingen. De server maakt voor
PDF-export geen permanent bestand; de preview staat alleen in Streamlit-sessiegeheugen en wordt na
verwijdering gewist. Een reeds gedownloade PDF valt buiten de serveropslag en blijft onder beheer
van de gebruiker.

## Handmatige AT-06-acceptatie

Na de functionele dashboard- en PDF-beoordeling is de runtime-meetronde via de bevestigingsdialog
verwijderd. Het privacyveilige activiteitenlog registreerde status `SUCCEEDED` met:

- 18 verwijderde netwerkvondsten;
- 18 verwijderde scores;
- 54 verwijderde scorefactoren;
- 1 verwijderde zonesnapshot;
- `verification_remaining` met waarde `0`.

Een afzonderlijke databasecontrole bevestigde daarna nul meetronden, nul netwerkvondsten en nul
scorefactoren. Daarmee is AT-06 voor deze functionele meetronde geslaagd.

Na de succesvolle verwijdering verscheen bij de overgang vanuit een eerder geopende PDF-preview
een Streamlit-fout doordat twee dialogstatussen tegelijk actief bleven. Dit had geen invloed op de
verwijderactie of nacontrole. De UI is daarna aangepast naar één exclusieve `active_dialog`-status
en de overgang PDF-preview naar verwijdermodal is als regressietest toegevoegd.
