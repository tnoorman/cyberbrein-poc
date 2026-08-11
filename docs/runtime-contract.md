# Runtimecontract van de launcher

Dit contract beschermt bestaand gedrag tijdens de geplande scheiding tussen CLI en
workflowcoördinatie.

## Publieke bediening

De launcher behoudt de commando's `run`, `resume`, `dashboard`, `discard`, `setup-monitor` en
`teardown-monitor`, inclusief de bestaande flags en `CYBERBREIN_*`-omgevingsvariabelen.
`./cyberbrein`, `python -m cyberbrein.workflow` en de geïnstalleerde `cyberbrein`-entrypoint blijven
dezelfde `main`-functie gebruiken.

## Veiligheidsinvarianten

- `run`, `resume`, `dashboard` en `discard` weigeren uitvoering als root.
- Alleen Collection wordt vanuit `run` via `sudo` gestart; Pipeline en Streamlit draaien als de
  normale gebruiker.
- Monitor-setup en -teardown vereisen juist root.
- Een meetronde-ID bevat uitsluitend letters, cijfers, punten, underscores en koppeltekens, begint
  met een alfanumeriek teken en is maximaal 128 tekens lang.
- Interface- en GPS-preflight vinden plaats voordat runtimebestanden worden gemaakt.
- `run` controleert daarvoor read-only of Storage al een verwerkte meetronde bevat. Bij een
  bestaande ronde of een onbereikbare Storage stopt de workflow zonder Collection of
  runtimebestanden te starten.
- Bronbuffer en secret worden exclusief als mode `0600` gemaakt in private runtimedirectories.
- Ruwe invoer wordt pas verwijderd nadat PostGIS-opslag is geverifieerd, of na een expliciet
  bevestigd `discard`.
- Een herstelbare fout bewaart bronbuffer en secret; een lege mislukte poging mag veilig worden
  opgeruimd.
- Ruwe BSSID, SSID, secret en precieze observatie-inhoud verschijnen niet in gebruikersmeldingen
  of het activiteitenlog.
- Een bestaande verwerkte ronde wordt nooit automatisch door `run` verwijderd. De gebruiker
  verwijdert deze pas na inzichtverstrekking via de bevestigde Operations-actie in het dashboard.

## Exitcodes

- `0`: de gevraagde handeling is geslaagd.
- `2`: configuratie, preflight, privilege of onveilig runtimebestand.
- `3`: Ingestion, Processing, Storage of opslagverificatie is mislukt.
- `4`: Storage is geverifieerd, maar cleanup is onvolledig.
- `5`: de geldige bron bevat onder het gekozen beleid geen bruikbare waarnemingen.
- `127`: een vereist programma ontbreekt.
- `130`: de gebruiker heeft de workflow onderbroken.

De unit- en integratietests voor `workflow`, `pipeline`, `collection` en `operations` bewaken dit
contract. Alleen een expliciete ADR mag een van deze afspraken wijzigen.
