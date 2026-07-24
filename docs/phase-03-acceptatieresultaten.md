# Fase 3 acceptatieresultaten

## Geautomatiseerde verificatie

De volledige regressiesuite is op 24 juli 2026 uitgevoerd:

- Ruff: geslaagd;
- pytest: 177 tests geslaagd;
- werkboom vóór de hardwaretest: schoon.

De scoregrenzen zijn met expliciete grensgevallen getest:

- RSSI: onder -80, -80, -67 en boven -67 dBm;
- waarnemingsfrequentie: 1, 2, 9, 10 en 300;
- totaalscore en kleur: 0/2 groen, 3/5 geel en 6/8 rood;
- encryptie: WPA2, WPA3 en Enterprise veiligere categorie; WPA1/WEP verouderd;
  onbekend als onbekend; open als hoogste bijdrage.

## Hardwaretest

De gestandaardiseerde meetronde gebruikte:

- duur: 60 seconden;
- kanalen: 36, 40, 44 en 48;
- dwell-tijd: 1 seconde;
- GPS-fix verplicht;
- maximale GPS-onnauwkeurigheid voor Processing: 25 meter;
- één vooraf goedgekeurde WGS84-zone.

Veilige resultaten:

- Collection: 1461 opgeslagen waarnemingen en 0 ontbrekende GPS-fixes;
- Ingestion: 1461 geaccepteerd en 0 afgewezen;
- Processing: 1022 geaccepteerd en 439 afgewezen wegens `gps_accuracy_exceeded`;
- aggregatie: 17 netwerkvondsten;
- scoreopslag: 51 factorregels, exact drie per netwerkvondst;
- factoren: 17 keer signaalsterkte, 17 keer encryptietype en 17 keer
  waarnemingsfrequentie;
- frequentiecategorieën: 3 incidenteel, 3 meerdere keren en 11 vaak;
- kleurverdeling: 6 groen en 11 geel;
- ongeldige score/kleur-combinaties: 0.

## Privacy en lifecycle

- Storage is atomisch geschreven en teruggelezen.
- Storage-rechten zijn `600`.
- Storage bevat geen kolommen voor BSSID, SSID, secret of ruwe observaties.
- De tijdelijke Collection-buffer, eventuele SQLite-sidecars en het meetrondesecret zijn na
  opslagverificatie verwijderd.
- De meetadapter is na Collection automatisch hersteld naar `managed/disconnected`.
- Er zijn tijdens de controles geen netwerk-ID's, SSID's, BSSID's of coördinaten afgedrukt.

Hiermee voldoet de fase-3-runtime aan het drie-factorenmodel uit tabellen 20 tot en met 22 en aan
de vastgelegde privacy- en cleanupgrenzen.
