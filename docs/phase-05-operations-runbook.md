# Fase 5: Operations-runbook

Dit runbook beschrijft de definitieve verwijdering van een afgeronde meetronde volgens FR-10.
Voer de actie pas uit nadat de inzichten zijn verstrekt en een gewenste PDF lokaal is opgeslagen.

## Configuratie

Het dashboard gebruikt dezelfde `CYBERBREIN_DATABASE_URL` als de pipeline en Presentation.
Het privacyveilige activiteitenlog staat standaard in:

```text
data/logs/operations.jsonl
```

Een andere locatie kan vóór het starten van Streamlit worden ingesteld:

```bash
export CYBERBREIN_ACTIVITY_LOG_PATH="/afgesproken/pad/operations.jsonl"
```

Het logbestand krijgt rechten `600`. Het bevat alleen UTC-tijd, actietype, uitkomst en
geaggregeerde aantallen. Meetronde-ID's, netwerk-ID's, BSSID's, SSID's en coördinaten worden niet
gelogd.

## Verwijderen via het dashboard

1. Open de actieve meetronde en controleer dat de inzichten zijn verstrekt.
2. Download zo nodig eerst de PDF; de server bewaart geen PDF-bestanden.
3. Klik op **Meetdata verwijderen**.
4. Controleer de getoonde meetronde en het ongefilterde aantal netwerkvondsten.
5. Lees de waarschuwing en vink de expliciete bevestiging aan.
6. Klik op **Bevestig verwijdering**.

Storage verwijdert de `measurement_round`. De gekoppelde zones, netwerkvondsten, scores en
scorefactoren worden via database-cascades hard verwijderd. Operations voert daarna een
afzonderlijke controlequery uit. Alleen wanneer alle vijf tellingen nul zijn, toont het dashboard
succes en wist het de geselecteerde netwerkvondst en PDF-preview uit de Streamlit-sessie.

## Controle

Controleer dat het dashboard meldt dat geen verwerkte meetronde beschikbaar is. De volgende query
moet uitsluitend nullen teruggeven:

```bash
psql cyberbrein_poc -c "
SELECT
  (SELECT count(*) FROM measurement_round) AS meetronden,
  (SELECT count(*) FROM zone) AS zones,
  (SELECT count(*) FROM network_finding) AS netwerkvondsten,
  (SELECT count(*) FROM network_score) AS scores,
  (SELECT count(*) FROM score_factor) AS scorefactoren;
"
```

Controleer vervolgens het log zonder de inhoud naar externe systemen te kopiëren:

```bash
stat -c 'Logrechten: %a' data/logs/operations.jsonl
tail -n 1 data/logs/operations.jsonl
```

Verwacht rechten `600`, status `SUCCEEDED` en `verification_remaining` met waarde `0`.

## Foutafhandeling

- Zonder bevestigingscheckbox kan de verwijderknop niet worden gebruikt.
- Een onbekende meetronde geldt niet als succesvolle verwijdering.
- Bij een database- of verificatiefout blijft het dashboard beschikbaar en verschijnt een veilige
  foutmelding.
- Een mislukte poging krijgt status `FAILED` in het activiteitenlog, zonder fouttekst of
  identifiers.
- Een gedownloade PDF staat op het apparaat van de gebruiker en kan niet door de server worden
  verwijderd; Cyberbrein beheert die kopie volgens de afgesproken gegevenscyclus.
