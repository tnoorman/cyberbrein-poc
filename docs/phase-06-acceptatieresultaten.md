# Fase 6: acceptatieresultaten

## Geautomatiseerde UI-controles

- De verwijderdialog blokkeert de definitieve knop totdat de gebruiker expliciet bevestigt.
- Filterwaarden blijven tijdelijk binnen het formulier en veranderen de resultaten pas na
  **Filters toepassen**.
- **Filters wissen** herstelt lege filtersets.
- Een geselecteerde netwerkvondst opent een afzonderlijk scherm met scorefactoren en technische
  metadata; de oude dictionary- en dataframeweergave zijn niet aanwezig.
- De PDF-actie opent een preview en biedt de downloadknop aan.
- Kaart-, PDF-, privacy-, Operations- en PostGIS-tests blijven onderdeel van de volledige suite.
- Ruff-format en Ruff-lint zijn groen; alle 201 tests slagen.

## Lokale runtime-rooktest

De vernieuwde applicatie is read-only tegen de bestaande runtime-demodata uitgevoerd. De
Streamlit-testharness rapporteerde geen applicatiefouten en toonde 18 netwerkvondsten, 12 vondsten
met verhoogde aandacht en 0 met hoge aandacht. De acties **Exporteer PDF** en
**Meetdata verwijderen** waren beschikbaar.

Daarna is Streamlit uitsluitend op `127.0.0.1:8501` gestart. De health-endpoint antwoordde `ok` en
de server is vervolgens gecontroleerd gestopt. De runtime-meetronde is niet gewijzigd of
verwijderd.

## Relatie met de mock-ups

- Figuur 9: KPI-kaarten, kaartcontext, actiebalk en privacytoelichting zijn overgenomen.
- Figuur 10: filters staan in een overlay met expliciet toepassen en wissen.
- Figuur 11: de definitieve verwijderwaarschuwing, aantallen en checkbox zijn aanwezig.
- Figuur 12: detail is een bewust gekozen afzonderlijke weergave met scorebalken en metadataraster.
- Figuur 13: PDF-preview en download staan samen in een grote previewdialog.

De uitvoering is niet pixel-perfect: native Streamlit-componenten en responsive gedrag hebben
voorrang boven vaste desktopafmetingen.

## Open handmatig acceptatiepunt

Na merge wordt het dashboard tijdelijk op `0.0.0.0` gestart voor controle vanaf een telefoon.
Daarbij worden leesbaarheid, knopvolgorde, filterbediening, detailnavigatie, PDF-preview en
verwijdermodal visueel beoordeeld. De definitieve verwijderknop wordt tijdens deze UI-controle niet
bevestigd, zodat de functionele demodata beschikbaar blijft voor de latere hardwareacceptatie.
