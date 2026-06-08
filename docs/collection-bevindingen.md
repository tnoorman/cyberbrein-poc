# Collection-spike bevindingen

De technische proef toont aan dat de meetopstelling passieve Wi-Fi-managementframes kan ontvangen via de TP-Link Archer T2U Plus in monitor mode. De collector heeft op 5 GHz beacon- en probe-responseframes ontvangen en opgeslagen in SQLite.

De VK-162 GPS-ontvanger levert via gpsd een 3D-fix met latitude en longitude. Na samenvoeging van Wi-Fi en GPS bevat elke geaccepteerde waarneming een tijdstempel, gepseudonimiseerde BSSID, signaalmetadata, kanaal, band, encryptietype en GPS-coördinaat.

De test is uitgevoerd als technische spike. De volgende stap is het opsplitsen van het script in modules voor Collection, GPS-provider, channel hopping en opslag.
