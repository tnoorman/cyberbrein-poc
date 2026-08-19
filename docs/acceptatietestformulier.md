# Acceptatietest Cyberbrein Wi-Fi Exposure PoC

| Documentgegeven | In te vullen |
|---|---|
| Acceptant | Henk van Ee |
| Organisatie | Cyberbrein |
| Testdatum |  |
| Starttijd |  |
| Eindtijd |  |
| Testlocatie |  |
| Testbegeleider |  |
| PoC-versie / Git-commit |  |
| Runbookversie |  |
| Meetronde |  |
| Testomgeving |  |

## 1. Doel van de acceptatietest

Deze acceptatietest toetst of de Cyberbrein Wi-Fi Exposure PoC bruikbaar is voor Cyberbrein.
Henk van Ee beoordeelt als acceptant of het dashboard de digitale blootstelling begrijpelijk
toont en of de score-uitleg zonder mondelinge toelichting van de ontwikkelaar te volgen is.

De kern van de acceptatie is niet alleen of een netwerkvondst groen, geel of rood op de kaart
staat, maar vooral of de acceptant zelfstandig kan herleiden waarom die kleur en score zijn
toegekend.

De test beoordeelt het gedrag van de PoC als geheel en hoort daarmee bij het hoogste testniveau
van het V-model. De aanpak is requirements-based: iedere teststap is gekoppeld aan een of meer
acceptatiecriteria en requirements.

## 2. Instructie voor acceptant en testbegeleider

### Voor Henk van Ee

1. Voer de stappen in hoofdstuk 7 in de aangegeven volgorde uit.
2. Noteer bij iedere stap wat je daadwerkelijk ziet en ervaart.
3. Kruis per stap precies één uitkomst aan: **Geslaagd**, **Niet geslaagd** of **Geblokkeerd**.
4. Beoordeel wat de PoC tijdens deze test laat zien; ga niet uit van wat de ontwikkelaar zegt dat
   het systeem zou moeten doen.
5. Noteer onduidelijke teksten, ontbrekende informatie en verbetersuggesties direct bij de stap.
6. Geef bij de score-uitleg in je eigen woorden aan waarom de geselecteerde vondst haar kleur
   heeft gekregen.

### Voor de testbegeleider

- Bereid alleen de omgeving en testmeetronde voor.
- Help bij technische bediening wanneer Henk daarom vraagt, maar vertel vóór afronding van
  AT-02 niet hoe de geselecteerde score moet worden geïnterpreteerd.
- Stuur Henk niet naar een gewenst antwoord en vul zijn oordeel niet namens hem in.
- Leg alleen privacyveilig bewijs vast: geen originele BSSID, ruwe SSID, bedrijfsnaam, adres,
  exacte access-pointlocatie of precieze coördinaten.
- Voer de databasecontrole bij AT-06 uit terwijl Henk de uitkomst kan zien.
- Voer de definitieve verwijdering pas uit nadat dashboard, detailweergave, privacygrenzen en
  PDF-export volledig zijn beoordeeld.

## 3. Acceptatiecriteria

De nummering en inhoud van deze tabel sluiten aan op Tabel 26 uit het verslag.

| ID | Onderdeel | Acceptatiecriterium | Gekoppelde requirements |
|---|---|---|---|
| AT-01 | Dashboardkaart | De acceptant kan op de kaart zien welke netwerkvondsten beperkte, verhoogde of hoge aandacht vragen. | FR-07 |
| AT-02 | Uitlegbaarheid score | De acceptant kan per netwerkvondst herleiden waarom de score groen, geel of rood is, zonder toelichting van de ontwikkelaar. | FR-06, NFR-02 |
| AT-03 | Privacygrens | De weergave koppelt netwerkvondsten niet direct aan een bedrijf, persoon, apparaat of bewezen access-pointlocatie. | FR-03, FR-05, FR-08, NFR-01 |
| AT-04 | Detailweergave | Detailinformatie verschijnt pas nadat de gebruiker bewust een netwerkvondst selecteert. | FR-08 |
| AT-05 | PDF-export | De PDF-export bevat de kaartweergave, scorekleur en score-uitleg die nodig zijn om het resultaat van een meetronde te bespreken. | FR-09 |
| AT-06 | Dataverwijdering | Na verwijdering bevat Storage geen records meer van de afgeronde meetronde. | FR-10 |
| AT-07 | Overdraagbaarheid | De acceptant kan aan de hand van het runbook volgen hoe een nieuwe meetronde wordt uitgevoerd, bekeken, geëxporteerd en verwijderd. | NFR-04 |

## 4. Beoordelingsregels

Gebruik bij iedere stap één van de volgende uitkomsten:

| Uitkomst | Betekenis |
|---|---|
| Geslaagd | Het werkelijke resultaat komt overeen met het verwachte resultaat en het gekoppelde criterium is aantoonbaar behaald. |
| Niet geslaagd | De stap kan worden uitgevoerd, maar het gedrag wijkt inhoudelijk af van het verwachte resultaat of is voor de acceptant onvoldoende begrijpelijk. |
| Geblokkeerd | De stap kan niet betrouwbaar worden uitgevoerd door een probleem met omgeving, testdata, hardware of een eerdere noodzakelijke stap. |

Een stap is niet automatisch geslaagd omdat de applicatie geen foutmelding geeft. De acceptant
beoordeelt ook begrijpelijkheid, privacygrenzen en bruikbaarheid.

Voorgestelde beslisregel voor de totale acceptatie:

- **Geaccepteerd:** alle criteria AT-01 t/m AT-07 zijn geslaagd;
- **Voorwaardelijk geaccepteerd:** alleen vooraf overeengekomen kleine bevindingen staan open en
  beïnvloeden privacy, verwijdering, begrijpelijkheid of kerngebruik niet;
- **Niet geaccepteerd:** minimaal één criterium is niet geslaagd of geblokkeerd en er is geen
  afdoende hertest uitgevoerd.

Het definitieve acceptatiebesluit blijft bij Cyberbrein en wordt in hoofdstuk 10 vastgelegd.

## 5. Testgegevens en privacyvoorwaarden

De acceptatietest wordt handmatig uitgevoerd met één verwerkte testmeetronde in de PoC-omgeving.
De testmeetronde bevat:

- netwerkvondsten;
- drie uitlegbare scorefactoren per netwerkvondst;
- scorekleuren en scores;
- een vooraf goedgekeurde zonepolygoon;
- voldoende variatie om de beschikbare filters zichtbaar te beoordelen.

De volgende herkenbare waarden mogen niet zichtbaar zijn in dashboard, PDF-export, screenshots,
video of verslagbewijs:

- originele BSSID's;
- ruwe SSID-tekst;
- namen van bedrijven of personen;
- adressen;
- identifiers die rechtstreeks naar een fysiek apparaat leiden;
- een als bewezen gepresenteerde access-pointlocatie;
- precieze losse observaties of coördinaten.

Een pseudonieme netwerk-ID mag in de detailweergave worden gebruikt zolang deze niet rechtstreeks
naar een persoon, bedrijf of apparaat te herleiden is.

## 6. Voorbereiding en startvoorwaarden

Vul deze controle vóór de eigenlijke acceptatietest in.

| Nr. | Startvoorwaarde | Controle | Resultaat / toelichting |
|---|---|---|---|
| V-01 | De te beoordelen PoC-versie is vastgelegd. | [ ] Gereed [ ] Niet gereed |  |
| V-02 | De test vindt plaats in de afgesproken PoC-omgeving. | [ ] Gereed [ ] Niet gereed |  |
| V-03 | PostgreSQL/PostGIS is bereikbaar. | [ ] Gereed [ ] Niet gereed |  |
| V-04 | Precies één verwerkte testmeetronde is beschikbaar. | [ ] Gereed [ ] Niet gereed |  |
| V-05 | De meetronde bevat netwerkvondsten, scorefactoren en een goedgekeurde zonepolygoon. | [ ] Gereed [ ] Niet gereed |  |
| V-06 | De testdata bevat voldoende variatie voor de te beoordelen filters en score-uitleg. | [ ] Gereed [ ] Niet gereed |  |
| V-07 | Het dashboard is alleen lokaal of via de afgesproken beveiligde testverbinding bereikbaar. | [ ] Gereed [ ] Niet gereed |  |
| V-08 | Het actuele runbook is beschikbaar voor AT-07. | [ ] Gereed [ ] Niet gereed |  |
| V-09 | Er is een veilige locatie afgesproken voor de tijdelijke PDF-download. | [ ] Gereed [ ] Niet gereed |  |
| V-10 | De acceptant weet dat AT-06 de testmeetronde definitief verwijdert. | [ ] Gereed [ ] Niet gereed |  |
| V-11 | Schermopname of screenshots zijn zo ingesteld dat geen verboden herkenbare waarden worden vastgelegd. | [ ] Gereed [ ] Niet gereed |  |

### Technische voorbereiding door testbegeleider

Start het dashboard als normale gebruiker:

```bash
cd /home/cyberbrein/poc
./cyberbrein dashboard
```

Open vervolgens:

```text
http://127.0.0.1:8501
```

Gebruik geen `sudo` en bind het dashboard niet publiek. De acceptatietest kan pas beginnen als alle
noodzakelijke startvoorwaarden gereed zijn. Noteer een niet-oplosbaar voorbereidingsprobleem in
hoofdstuk 9 en plan zo nodig een nieuwe testsessie.

## 7. Uitvoering acceptatietest

### Stap 1 — Dashboard met testmeetronde openen

**Actie**

Open het dashboard met de voorbereide, verwerkte testmeetronde. Wacht totdat de kaart en
samenvattende aantallen volledig zijn geladen.

**Gekoppeld aan:** AT-01, FR-07

**Verwacht resultaat**

Het dashboard opent met de goedgekeurde zone en toont netwerkvondsten als gekleurde bolletjes op
de kaart. De betekenis van beperkte, verhoogde en hoge aandacht is zonder mondelinge uitleg te
onderscheiden.

**In te vullen door Henk**

Wat zag je bij het openen van het dashboard?

....................................................................................................

....................................................................................................

Was duidelijk wat de kleuren op de kaart betekenen?

[ ] Ja  [ ] Nee  [ ] Gedeeltelijk

Toelichting:

....................................................................................................

**Uitkomst stap 1:** [ ] Geslaagd  [ ] Niet geslaagd  [ ] Geblokkeerd

**Bewijsreferentie, indien gebruikt:** ..............................................................

### Stap 2 — Filters gebruiken

**Actie**

1. Open **Filters**.
2. Probeer achtereenvolgens band, kanaal, encryptietype en scorekleur.
3. Klik na de gekozen waarden op **Filters toepassen**.
4. Controleer of kaart en aantallen veranderen.
5. Klik op **Filters wissen** en controleer of de volledige meetronde terugkomt.

**Gekoppeld aan:** AT-01, FR-07

**Verwacht resultaat**

De kaart past de getoonde netwerkvondsten aan op basis van de gekozen filters. Wijzigingen worden
pas actief na **Filters toepassen**. **Filters wissen** herstelt de volledige meetronde.

**In te vullen door Henk**

| Filter | Was het filter vindbaar? | Veranderde de selectie begrijpelijk? | Opmerking |
|---|---|---|---|
| Band | [ ] Ja [ ] Nee | [ ] Ja [ ] Nee [ ] Niet zichtbaar in testdata |  |
| Kanaal | [ ] Ja [ ] Nee | [ ] Ja [ ] Nee [ ] Niet zichtbaar in testdata |  |
| Encryptietype | [ ] Ja [ ] Nee | [ ] Ja [ ] Nee [ ] Niet zichtbaar in testdata |  |
| Scorekleur | [ ] Ja [ ] Nee | [ ] Ja [ ] Nee [ ] Niet zichtbaar in testdata |  |

Wat gebeurde er na **Filters wissen**?

....................................................................................................

**Uitkomst stap 2:** [ ] Geslaagd  [ ] Niet geslaagd  [ ] Geblokkeerd

**Bewijsreferentie, indien gebruikt:** ..............................................................

### Stap 3 — Bewust een netwerkvondst selecteren

**Actie**

1. Controleer eerst of zonder selectie alleen het kaartoverzicht zichtbaar is.
2. Selecteer bewust één netwerkvondst op de kaart.
3. Open bij een cluster eerst het cluster en selecteer daarna één marker.

**Gekoppeld aan:** AT-04, FR-08

**Verwacht resultaat**

De detailweergave verschijnt pas na de bewuste selectie. De weergave toont geen originele BSSID,
ruwe SSID-tekst of bewezen access-pointlocatie.

**In te vullen door Henk**

Verscheen detailinformatie vóórdat je een vondst selecteerde?

[ ] Nee  [ ] Ja  [ ] Niet vast te stellen

Verscheen de detailweergave direct na jouw bewuste selectie?

[ ] Ja  [ ] Nee  [ ] Gedeeltelijk

Welke informatie zag je in de detailweergave?

....................................................................................................

....................................................................................................

**Uitkomst stap 3:** [ ] Geslaagd  [ ] Niet geslaagd  [ ] Geblokkeerd

**Bewijsreferentie, indien gebruikt:** ..............................................................

### Stap 4 — Scorefactoren zelfstandig uitleggen

**Belangrijk:** de ontwikkelaar of testbegeleider geeft tijdens deze stap geen inhoudelijke uitleg
over de score. Henk beoordeelt de informatie die de PoC zelf toont.

**Actie**

Bekijk van de geselecteerde netwerkvondst de score, kleur en drie scorefactoren. Leg daarna in je
eigen woorden uit waarom deze vondst groen, geel of rood is.

**Gekoppeld aan:** AT-02, FR-06, NFR-02

**Verwacht resultaat**

De score is zelfstandig te herleiden op basis van factor, categorie, waargenomen waarde, punten en
weging. De uitleg maakt begrijpelijk hoe de getoonde totaalscore en kleur tot stand komen.

**In te vullen door Henk**

Getoonde kleur: [ ] Groen  [ ] Geel  [ ] Rood

Getoonde totaalscore: .......... van 8

| Scorefactor | Wat begrijp je uit de getoonde waarde en categorie? | Getoonde punten/weging waren duidelijk? |
|---|---|---|
| Signaalsterkte |  | [ ] Ja [ ] Nee [ ] Gedeeltelijk |
| Encryptietype |  | [ ] Ja [ ] Nee [ ] Gedeeltelijk |
| Waarnemingsfrequentie |  | [ ] Ja [ ] Nee [ ] Gedeeltelijk |

Waarom heeft deze netwerkvondst volgens jou deze kleur?

....................................................................................................

....................................................................................................

....................................................................................................

Kon je dit herleiden zonder mondelinge toelichting van de ontwikkelaar?

[ ] Ja  [ ] Nee  [ ] Gedeeltelijk

Welke tekst of informatie was eventueel onduidelijk of ontbrak?

....................................................................................................

**Uitkomst stap 4:** [ ] Geslaagd  [ ] Niet geslaagd  [ ] Geblokkeerd

**Bewijsreferentie, indien gebruikt:** ..............................................................

### Stap 5 — Privacygrenzen controleren

**Actie**

Controleer het kaartoverzicht en de detailweergave op directe herleidbaarheid. Beoordeel ook de
privacytoelichting bij de kaart en de begrenzing van de exposure-score.

**Gekoppeld aan:** AT-03, FR-03, NFR-01

**Verwacht resultaat**

De weergave koppelt netwerkvondsten niet direct aan een persoon, bedrijf, apparaat of exacte
fysieke locatie. De applicatie presenteert een kaartpunt niet als bewezen access-pointlocatie.

**In te vullen door Henk**

| Controlepunt | Aangetroffen? | Toelichting |
|---|---|---|
| Originele BSSID zichtbaar | [ ] Nee [ ] Ja [ ] Onzeker |  |
| Ruwe SSID-tekst zichtbaar | [ ] Nee [ ] Ja [ ] Onzeker |  |
| Bedrijfs- of persoonsnaam zichtbaar | [ ] Nee [ ] Ja [ ] Onzeker |  |
| Direct herleidbaar apparaat zichtbaar | [ ] Nee [ ] Ja [ ] Onzeker |  |
| Exacte locatie als bewezen AP-locatie gepresenteerd | [ ] Nee [ ] Ja [ ] Onzeker |  |
| Privacybegrenzing bij kaart begrijpelijk | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |
| Begrenzing van de exposure-score begrijpelijk | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |

Waarom vind je de weergave wel of niet voldoende privacybegrensd?

....................................................................................................

....................................................................................................

**Uitkomst stap 5:** [ ] Geslaagd  [ ] Niet geslaagd  [ ] Geblokkeerd

**Bewijsreferentie, indien gebruikt:** ..............................................................

### Stap 6 — PDF-export genereren en beoordelen

**Actie**

1. Ga terug naar het kaartoverzicht.
2. Stel de filters in die in het rapport moeten terugkomen.
3. Klik op **Exporteer PDF**.
4. Controleer de preview.
5. Klik op **Download PDF** en sla het bestand tijdelijk op de afgesproken beveiligde locatie op.

**Gekoppeld aan:** AT-05, FR-09

**Verwacht resultaat**

De PDF bevat de kaartweergave, scorekleur en score-uitleg die nodig zijn om het resultaat van een
meetronde te bespreken. De PDF bevat geen originele BSSID, ruwe SSID-tekst, bedrijfsnamen,
adressen of exacte access-pointlocaties.

**In te vullen door Henk**

| Controlepunt PDF | Resultaat | Toelichting |
|---|---|---|
| PDF-preview wordt zonder applicatiefout geopend | [ ] Ja [ ] Nee |  |
| Actieve filters zijn herkenbaar | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |
| Kaartweergave is aanwezig | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |
| Scorekleuren zijn begrijpelijk | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |
| Scorefactoren en uitleg zijn aanwezig | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |
| Rapport is bruikbaar om de meetronde te bespreken | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |
| Verboden herkenbare waarden aangetroffen | [ ] Nee [ ] Ja [ ] Onzeker |  |
| Download is gelukt | [ ] Ja [ ] Nee |  |

Welke informatie in de PDF vond je het meest bruikbaar?

....................................................................................................

Wat ontbreekt of is onduidelijk?

....................................................................................................

**Uitkomst stap 6:** [ ] Geslaagd  [ ] Niet geslaagd  [ ] Geblokkeerd

**Bewijsreferentie / bestandsnaam:** .................................................................

### Stap 7 — Meetdata definitief verwijderen

**Let op:** dit is de laatste systeemactie. De testmeetronde wordt definitief uit Storage
verwijderd. Voer deze stap pas uit wanneer stap 1 t/m 6 volledig zijn beoordeeld en de gewenste PDF
is gedownload.

**Actie in het dashboard**

1. Klik op **Meetdata verwijderen**.
2. Controleer de geselecteerde meetronde en het ongefilterde aantal netwerkvondsten.
3. Lees de definitieve waarschuwing.
4. Vink de expliciete bevestiging aan.
5. Klik op **Bevestig verwijdering**.
6. Controleer of het dashboard daarna meldt dat geen verwerkte meetronde beschikbaar is.

**Gekoppeld aan:** AT-06, FR-10

**Verwacht resultaat**

Storage bevat na verwijdering geen records meer van de afgeronde meetronde. Een afzonderlijke
controlequery bevestigt dit.

**Technische nacontrole door testbegeleider**

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

Alle vijf tellingen moeten `0` zijn.

**In te vullen door Henk en testbegeleider**

| Controlepunt | Werkelijk resultaat |
|---|---|
| Verwijderknop bleef geblokkeerd vóór expliciete bevestiging | [ ] Ja [ ] Nee |
| Dashboard gaf een succesmelding na bevestiging | [ ] Ja [ ] Nee |
| Dashboard meldde daarna dat geen verwerkte meetronde beschikbaar is | [ ] Ja [ ] Nee |
| `measurement_round` | .......... records |
| `zone` | .......... records |
| `network_finding` | .......... records |
| `network_score` | .......... records |
| `score_factor` | .......... records |

Aanvullende waarneming:

....................................................................................................

**Uitkomst stap 7:** [ ] Geslaagd  [ ] Niet geslaagd  [ ] Geblokkeerd

**Bewijsreferentie, indien gebruikt:** ..............................................................

### Stap 8 — Overdraagbaarheid van het runbook beoordelen

**Actie**

Open het runbook en volg de hoofdlijn voor:

1. voorbereiding van een nieuwe meetronde;
2. starten van Collection en pipeline;
3. openen en gebruiken van het dashboard;
4. maken van een PDF-export;
5. verwijderen van de afgeronde meetdata;
6. herstellen of opruimen na een mislukte run.

Het is voor AT-07 niet nodig om na AT-06 direct een nieuwe echte meting te starten. Henk gebruikt
het runbook om de procedure zelfstandig terug te vinden en vertelt welke stappen hij zou volgen.

**Gekoppeld aan:** AT-07, NFR-04

**Verwacht resultaat**

Het runbook maakt duidelijk hoe een meetronde wordt gestart, bekeken, geëxporteerd en verwijderd.
De acceptant kan de benodigde hoofdstukken en commando's zonder mondelinge reconstructie door de
ontwikkelaar vinden.

**In te vullen door Henk**

| Onderdeel | Kon je de procedure zelfstandig vinden? | Was de procedure uitvoerbaar en duidelijk? | Opmerking |
|---|---|---|---|
| Voorbereiding / preflight | [ ] Ja [ ] Nee | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |
| Meetronde starten | [ ] Ja [ ] Nee | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |
| Pipeline en succes controleren | [ ] Ja [ ] Nee | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |
| Dashboard openen | [ ] Ja [ ] Nee | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |
| PDF exporteren | [ ] Ja [ ] Nee | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |
| Verwerkte meetdata verwijderen | [ ] Ja [ ] Nee | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |
| Onderbroken run hervatten of tijdelijke invoer verwijderen | [ ] Ja [ ] Nee | [ ] Ja [ ] Nee [ ] Gedeeltelijk |  |

Welke stappen zou je volgen om een nieuwe meetronde uit te voeren en af te ronden?

....................................................................................................

....................................................................................................

....................................................................................................

Welke onderdelen van het runbook moeten volgens jou duidelijker of korter?

....................................................................................................

**Uitkomst stap 8:** [ ] Geslaagd  [ ] Niet geslaagd  [ ] Geblokkeerd

**Bewijsreferentie, indien gebruikt:** ..............................................................

## 8. Samenvattend testformulier

Deze tabel volgt de structuur van Tabel 27 uit het verslag. Neem de uitkomsten van hoofdstuk 7
hier compact over.

| Stap | Gekoppelde criteria | Verwacht resultaat | Werkelijk resultaat | Geslaagd |
|---|---|---|---|---|
| Open het dashboard met een verwerkte testmeetronde. | AT-01, FR-07 | Het dashboard opent met de goedgekeurde zone en toont netwerkvondsten als gekleurde bolletjes op de kaart. |  | [ ] Ja [ ] Nee [ ] Geblokkeerd |
| Gebruik de filters voor band, kanaal, encryptietype en scorekleur. | AT-01, FR-07 | De kaart past de getoonde netwerkvondsten aan op basis van de gekozen filters. |  | [ ] Ja [ ] Nee [ ] Geblokkeerd |
| Selecteer bewust één netwerkvondst op de kaart. | AT-04, FR-08 | De detailweergave verschijnt pas na selectie en toont geen originele BSSID, ruwe SSID-tekst of bewezen access-pointlocatie. |  | [ ] Ja [ ] Nee [ ] Geblokkeerd |
| Bekijk de scorefactoren van de geselecteerde netwerkvondst. | AT-02, FR-06, NFR-02 | De score is te herleiden op basis van factor, categorie, waargenomen waarde, punten en weging. |  | [ ] Ja [ ] Nee [ ] Geblokkeerd |
| Controleer de privacygrenzen in dashboard en detailweergave. | AT-03, FR-03, NFR-01 | De weergave koppelt netwerkvondsten niet direct aan een persoon, bedrijf, apparaat of exacte fysieke locatie. |  | [ ] Ja [ ] Nee [ ] Geblokkeerd |
| Genereer een PDF-export van de meetronde. | AT-05, FR-09 | De PDF bevat kaartweergave, scorekleur en score-uitleg zonder verboden herkenbare waarden. |  | [ ] Ja [ ] Nee [ ] Geblokkeerd |
| Verwijder de meetdata van de afgeronde meetronde. | AT-06, FR-10 | Storage bevat na verwijdering geen records meer van de meetronde; de controlequery bevestigt dit. |  | [ ] Ja [ ] Nee [ ] Geblokkeerd |
| Volg het runbook voor de hoofdlijn van een meetronde. | AT-07, NFR-04 | Het runbook maakt duidelijk hoe een meetronde wordt gestart, bekeken, geëxporteerd en verwijderd. |  | [ ] Ja [ ] Nee [ ] Geblokkeerd |

## 9. Bevindingen en afwijkingen

Registreer iedere afwijking afzonderlijk. Verwijs bij een hertest naar hetzelfde bevinding-ID.

| Bevinding-ID | Teststap / criterium | Omschrijving | Ernst | Afgesproken actie | Eigenaar | Streefdatum | Hertestresultaat |
|---|---|---|---|---|---|---|---|
| BEV-01 |  |  | [ ] Blokkerend [ ] Hoog [ ] Middel [ ] Laag |  |  |  |  |
| BEV-02 |  |  | [ ] Blokkerend [ ] Hoog [ ] Middel [ ] Laag |  |  |  |  |
| BEV-03 |  |  | [ ] Blokkerend [ ] Hoog [ ] Middel [ ] Laag |  |  |  |  |
| BEV-04 |  |  | [ ] Blokkerend [ ] Hoog [ ] Middel [ ] Laag |  |  |  |  |

### Algemene opmerkingen van Henk

Wat werkt volgens jou goed?

....................................................................................................

....................................................................................................

Wat moet volgens jou worden verbeterd voordat de PoC goed overdraagbaar is?

....................................................................................................

....................................................................................................

## 10. Eindoordeel en ondertekening

### Resultaat per acceptatiecriterium

| Criterium | Geslaagd | Niet geslaagd | Geblokkeerd | Toelichting / bevinding-ID |
|---|---|---|---|---|
| AT-01 Dashboardkaart | [ ] | [ ] | [ ] |  |
| AT-02 Uitlegbaarheid score | [ ] | [ ] | [ ] |  |
| AT-03 Privacygrens | [ ] | [ ] | [ ] |  |
| AT-04 Detailweergave | [ ] | [ ] | [ ] |  |
| AT-05 PDF-export | [ ] | [ ] | [ ] |  |
| AT-06 Dataverwijdering | [ ] | [ ] | [ ] |  |
| AT-07 Overdraagbaarheid | [ ] | [ ] | [ ] |  |

### Acceptatiebesluit Cyberbrein

[ ] Geaccepteerd

[ ] Voorwaardelijk geaccepteerd

[ ] Niet geaccepteerd

Voorwaarden of motivatie:

....................................................................................................

....................................................................................................

....................................................................................................

| Ondertekening | Naam | Datum | Handtekening |
|---|---|---|---|
| Acceptant namens Cyberbrein | Henk van Ee |  |  |
| Testbegeleider / ontwikkelaar |  |  |  |

## 11. Bewijsregistratie

Neem alleen bewijs op dat nodig is om de acceptatie-uitkomst te onderbouwen. Gebruik een
privacyveilige bestandsnaam en neem geen verboden herkenbare waarden in bestandsnamen op.

| Bewijs-ID | Bestandsnaam of videoreferentie | Behoort bij stap | Privacy gecontroleerd door | Opmerking |
|---|---|---|---|---|
| B-01 |  |  |  |  |
| B-02 |  |  |  |  |
| B-03 |  |  |  |  |
| B-04 |  |  |  |  |

De belangrijkste stappen kunnen in de realisatievideo worden opgenomen. De video toont daarmee
dat de acceptatie niet alleen op papier is voorbereid, maar is getoetst aan werkend gedrag van de
PoC. Controleer vóór opname en vóór oplevering opnieuw dat originele BSSID's, ruwe SSID-tekst,
bedrijfsnamen, adressen en exacte fysieke locaties niet herkenbaar zijn.

## Bijlage A. Korte volgorde voor tijdens de testsessie

1. Vul documentgegevens en startvoorwaarden in.
2. Open het dashboard.
3. Beoordeel kaartkleuren en aandachtcategorieën.
4. Test band-, kanaal-, encryptie- en scorekleurfilters.
5. Selecteer bewust één netwerkvondst.
6. Laat Henk de score zonder mondelinge uitleg herleiden.
7. Controleer samen de privacygrenzen.
8. Genereer, beoordeel en download de PDF.
9. Verwijder als laatste systeemactie de meetronde en controleer vijf nultellingen.
10. Laat Henk de hoofdlijn in het runbook terugvinden.
11. Vul samenvatting, bevindingen en eindoordeel in.
12. Onderteken het formulier.

## Bijlage B. Conversie naar DOCX

Converteer het formulier met Pandoc:

```bash
pandoc docs/acceptatietestformulier.md \
  --from=gfm \
  --to=docx \
  --toc \
  --metadata title="Acceptatietest Cyberbrein Wi-Fi Exposure PoC" \
  --output=acceptatietestformulier-cyberbrein.docx
```

Gebruik voor de Cyberbrein-huisstijl eventueel een beheerd referentiedocument:

```bash
pandoc docs/acceptatietestformulier.md \
  --from=gfm \
  --to=docx \
  --toc \
  --reference-doc=cyberbrein-reference.docx \
  --output=acceptatietestformulier-cyberbrein.docx
```

Controleer na conversie of invulregels, selectievakjes, brede tabellen, paginawissels en
handtekeningvelden goed op de pagina staan. Werk daarna in Word of LibreOffice de inhoudsopgave
bij.
