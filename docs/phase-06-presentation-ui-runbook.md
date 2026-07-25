# Fase 6: Presentation-UI-runbook

De Presentation-UI volgt de structuur en visuele hiërarchie van figuren 9 tot en met 13 uit het
afstudeerverslag, met responsive Streamlit-componenten voor desktop en telefoon.

## Starten

Activeer de projectomgeving en stel de PostGIS-database in:

```bash
source .venv/bin/activate
export CYBERBREIN_DATABASE_URL="postgresql+psycopg2:///cyberbrein_poc"
streamlit run src/cyberbrein/presentation/app.py --server.address 127.0.0.1
```

Gebruik `0.0.0.0` alleen tijdelijk voor een afgesproken test vanaf een ander apparaat. Het
dashboard heeft geen applicatieauthenticatie en hoort na zo'n test weer te worden gestopt.

## Kaartoverzicht

- De drie kaarten tonen alle zichtbare netwerkvondsten, verhoogde aandacht en hoge aandacht.
- De labelloze wegenkaart toont scorekleuren, clusters en spiderfy bij samenvallende punten.
- De actiebalk bevat **Filters**, **Exporteer PDF** en **Meetdata verwijderen**.
- Op een smal scherm worden KPI's, acties en metadata onder elkaar geplaatst.

## Filters

Open **Filters**. Meetronde, band, encryptietype, scorekleur en signaalsterkte staan vooraan. Zone
en kanaal staan onder **Meer filters**.

- Wijzigingen binnen het formulier beïnvloeden de kaart nog niet.
- **Filters toepassen** activeert alle gekozen categorieën tegelijk.
- Het getal in de filterknop toont hoeveel filtergroepen actief zijn.
- **Filters wissen** herstelt de volledige meetronde.
- Een filterwijziging wist een oude markerselectie en PDF-preview.

## Detailweergave

Selecteer een marker, of eerst een cluster en daarna een uitgespreide marker. Presentation opent
een afzonderlijk detailscherm met:

- een verkorte pseudonieme netwerk-ID en optioneel de volledige pseudonieme waarde;
- totaalscore en aandachtkleur;
- precies drie scorefactoren met waargenomen waarde, categorie, punten, weging en uitleg;
- band, kanaal, frequentie, encryptietype, signaalsterkte, aantal waarnemingen en zone;
- de begrenzing dat dit geen volledig beveiligingsoordeel is.

Gebruik **Terug naar overzicht** om de detaildata weer te verbergen.

## PDF-preview

Klik op **Exporteer PDF**. De grote dialog genereert de preview voor de actieve filters en toont
daarna **Download PDF**. De kaartstijl blijft labelloos en gelijk aan het dashboard. De preview
blijft alleen in Streamlit-sessiegeheugen; de server maakt geen permanent PDF-bestand.

## Meetdata verwijderen

De verwijderactie gebruikt de fase-5-bevestigingsdialog en Operations-controles. Volg voor de
definitieve actie het aparte fase-5 Operations-runbook.
