# Toegepaste architectuur- en ontwerppatronen

Dit document benoemt alleen patronen die aantoonbaar in de implementatie aanwezig zijn. Het doel
is niet om zoveel mogelijk patroonlabels te gebruiken, maar om ontwerpkeuzes te koppelen aan een
concreet probleem en controleerbaar gevolg.

## Aanwezige patronen

- **Gelaagde architectuur:** de gegevensstroom loopt van Collection via Ingestion, Processing en
  Storage naar Presentation. De afhankelijkheidsregels staan in `architecture-boundaries.md`.
- **Repository:** `StorageRepository` schermt PostgreSQL/PostGIS-opslag af en
  `PresentationRepository` vormt een afzonderlijke alleen-lezen querygrens voor het dashboard.
- **Service Layer:** `CollectorService`, `IngestionService`, `ProcessingService`,
  `PipelineService` en `OperationsService` coördineren applicatiehandelingen zonder
  presentatiecode.
- **Ports and Adapters, doelgericht toegepast:** kleine `Protocol`-grenzen bestaan waar hardware,
  opslag of een test-double daadwerkelijk verwisselbaar moet zijn, bijvoorbeeld voor GPS,
  observatieopslag, channel hopping en PostGIS-opslag.
- **Dependency injection:** productie-implementaties worden via constructors of callables
  aangeboden. Hierdoor kunnen tests hardware en externe processen vervangen zonder globale
  toestand.
- **Functionele kern met imperatieve schil:** Processing bestaat hoofdzakelijk uit pure
  validatie-, normalisatie-, zone-, aggregatie- en scorefuncties; I/O blijft erbuiten.
- **Onveranderlijke value objects:** bevroren dataclasses controleren domeininvarianten bij
  constructie, waaronder scoretotalen, zone-uitkomsten en verwerkingstellingen.
- **Privacyveilige fouttaxonomie:** gecontroleerde fouten verlaten een subsysteem als een vaste
  categorie en niet als mogelijk gevoelige interne details.

`CachedGpsFixProvider` is daarnaast een concreet Adapter-voorbeeld: een push-georiënteerde
GPSD-stream wordt aangeboden als een actuele pull-georiënteerde GPS-fix voor Collection.

## Bewust niet geclaimd

- De verwisselbare test-callables vormen geen volwaardig **Strategy**-patroon; er is per geval
  slechts één productie-algoritme.
- De argparse-subcommands zijn geen **Command**-objecten.
- Eén callback vormt nog geen **Observer**-patroon.
- De scheiding tussen schrijf- en presentatierepositories is geen volledige **CQRS**-architectuur.
- Streamlit vormt geen formele **MVC**-implementatie.
- Een geïnjecteerde factory-callable is geen **Abstract Factory**.

Nieuwe patronen worden alleen toegevoegd wanneer een bestaand probleem, een tweede consument of
een tweede productie-implementatie de extra abstractie rechtvaardigt.
