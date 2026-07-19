# GRIB Weather Overlay voor Home Assistant

Toont GRIB-weerdata (wind, neerslag, temperatuur, druk, zicht, bewolking, ...)
als kleurenlaag over een [OpenSeaMap](https://map.openseamap.org)-kaart in
Home Assistant. Je kiest een tijdstip via een slider, of een begin/eind/stap
om een animatie van de voorspelling af te spelen.

Eerste databron: [KNMI Data Platform](https://dataplatform.knmi.nl/) (HARMONIE-AROME
model, Nederland). De integratie is opgezet met een `GribSource`-interface
zodat later andere bronnen toegevoegd kunnen worden zonder de kaart-kaart of
de rest van de backend te hoeven aanpassen.

## Features

- Configureerbare parameters: wind (10m), windstoten, temperatuur (2m),
  dauwpunt (2m), relatieve luchtvochtigheid (2m), neerslag, luchtdruk
  (zeeniveau), zicht, bewolking.
- Eén-tijdstip-slider én een animatiemodus (begin, eind, stap, afspeelsnelheid).
- Kaart-kaart met OpenStreetMap-basislaag + OpenSeaMap seamark-laag + de
  GRIB-overlay, volledig los van een internetverbinding voor de kaart-JS zelf
  (Leaflet wordt meegeleverd, geen CDN-afhankelijkheid voor de code — de
  kaarttegels van OSM/OpenSeaMap komen uiteraard wel van internet).
- Alleen de geconfigureerde parameters en het geconfigureerde tijdsbereik
  worden gedecodeerd/gerenderd; oudere forecast-runs worden automatisch
  opgeruimd (instelbaar).
- Nieuwe forecast-runs worden direct opgehaald via KNMI's MQTT Notification
  Service (in plaats van te wachten op de eerstvolgende poll), met het
  reguliere poll-interval als betrouwbare fallback als de MQTT-verbinding om
  wat voor reden dan ook niet lukt. Let op: de Notification Service
  autoriseert los van de Open Data API — het kan zijn dat je API-sleutel voor
  MQTT wordt geweigerd ("Not authorized") terwijl het downloaden gewoon werkt.
  Dan valt de integratie automatisch terug op pollen; de push-functie vereist
  een sleutel die óók op de Notification Service is geabonneerd (KNMI
  Developer Portal).

## Vereisten

- Home Assistant OS of Supervised. Alle dependencies zijn pure-Python /
  universele wheels (`numpy`, `Pillow`, `paho-mqtt`); GRIB1 wordt door een
  meegeleverde eigen decoder gelezen, dus er is géén `eccodes`/`cfgrib`
  binaire library nodig (die heeft niet voor elke Python-versie/CPU een wheel
  en brak eerder de installatie).
- Een gratis API-sleutel van het
  [KNMI Developer Portal](https://developer.dataplatform.knmi.nl/) voor de
  Open Data API.

## Installatie

### Via HACS (aanbevolen)

1. HACS → Integraties → menu (⋮) → Custom repositories.
2. Voeg de URL van deze repository toe, categorie "Integration".
3. Zoek "GRIB Weather Overlay" in HACS en installeer.
4. Herstart Home Assistant.

### Handmatig

1. Kopieer `custom_components/grib_overlay` naar `/config/custom_components/`.
2. Herstart Home Assistant.

## Configuratie

1. Instellingen → Apparaten & diensten → Integratie toevoegen → "GRIB Weather
   Overlay".
2. Kies de bron (KNMI Data Platform) en vul je Open Data API-sleutel in.
   Optioneel: vul ook een aparte **Notification Service API-sleutel** in voor
   directe push-updates bij een nieuwe forecast-run (zie hieronder). Laat dit
   veld leeg als je die niet hebt — dan wordt er periodiek gepolld.
3. Kies een dataset (standaard: HARMONIE-AROME Cy43, Nederland, near-surface
   parameters).
4. Kies welke parameters bijgehouden moeten worden.
5. Optioneel: pas via de integratie-opties de voorspellingshorizon (default
   24 uur), het aantal bewaarde forecast-runs (default 2), het poll-interval
   (default 30 minuten) en de Notification Service-sleutel aan. Via de opties
   kun je de notificatie-sleutel ook later toevoegen zonder de integratie
   opnieuw toe te voegen.

## Kaart toevoegen aan een dashboard

Voeg een kaart van het type `custom:grib-overlay-card` toe, bijvoorbeeld via
de YAML-editor van een dashboard:

```yaml
type: custom:grib-overlay-card
# optioneel: vast een specifieke integratie-instantie/parameter kiezen
# entry_id: <config entry id>
# parameter: wind_10m
# center: [52.1, 5.3]
# zoom: 7
# grootte in een Secties-dashboard:
# columns: full   # breedte: "full" (volledig, standaard) of een getal kolommen
# rows: 8         # hoogte in grid-rijen
# eenheden (nautisch):
# wind_unit: kn        # wind + windstoten: m/s (standaard), kn, km/h of mph
# visibility_unit: NM  # zicht: km (standaard) of NM (zeemijlen)
```

Zonder `entry_id`/`parameter` pakt de kaart automatisch de eerst
geconfigureerde integratie en het eerste geselecteerde parametertype, en kun
je in de kaart zelf wisselen.

### Grootte / layout

In een **Secties-dashboard** vult de kaart standaard de volledige breedte en
past de kaarthoogte zich aan de toegewezen cel aan. Je kunt de grootte op twee
manieren regelen:

- **Slepen** aan de rand van de kaart in de dashboard-editor.
- **In YAML** met `columns` (breedte: `full` of een aantal grid-kolommen) en
  `rows` (hoogte in grid-rijen). `rows` bepaalt ook de kaarthoogte in een
  gewoon (masonry) dashboard.

### Eenheden

Voor nautisch gebruik kun je in de kaart optioneel andere eenheden tonen. Dit
is puur een weergavekeuze in de kaart (de onderliggende data verandert niet):

- `wind_unit`: eenheid voor wind én windstoten — `m/s` (standaard), `kn`
  (knopen / zeemijlen per uur), `km/h` of `mph`.
- `visibility_unit`: eenheid voor zicht — `km` (standaard) of `NM` (zeemijlen).

De legenda en het label in de parameterkeuze worden dan automatisch omgerekend.

## Bekende beperkingen

- Eén HARMONIE-forecast-run bij KNMI is een tar-archief van ~850MB (alle
  lead times samen). Er is geen API om losse lead times te downloaden, dus
  elke nieuwe run kost die volledige download; alleen de lead times binnen de
  ingestelde voorspellingshorizon worden gedecodeerd en als PNG bewaard, de
  rest wordt direct weer verwijderd. Zet de horizon niet hoger dan nodig.
- Op dit moment wordt alleen de `harmonie_arome_cy43_p1`-dataset (Nederland,
  regular lat-lon grid) ondersteund. De Europese rotated-lat-lon varianten
  vereisen een extra reprojectiestap die nog niet is geïmplementeerd.
- Windpijltjes/particle-animatie (zoals Windy) is voorbereid
  (`renderMode: particles` staat al als optie in de kaart) maar nog niet
  geïmplementeerd — v1 toont alle parameters, inclusief wind, als gekleurde
  raster-overlay.

## Ontwikkelen & testen

```bash
python3 -m pip install -r requirements-dev.txt  # numpy, Pillow, paho-mqtt, homeassistant, pytest-homeassistant-custom-component
python3 -m pytest tests/
```

Twee losse dev-scripts werken zonder Home Assistant:

- `dev/verify_knmi_source.py` — controleert de KNMI-source-implementatie
  tegen de echte Open Data API (dataset-catalogus, file listing, download-URL).
- `dev/render_preview.py <grib-bestand>` — decodeert en rendert alle
  geconfigureerde parameters uit één GRIB-lead-time-bestand naar PNG's in
  `dev/output/`, handig om colormaps/reprojectie visueel te controleren.
- `dev/mock_server.py` + `dev/dev.html` — draait de kaart-kaart in een echte
  browser tegen een nagebootste API (hergebruikt de PNG's uit
  `dev/render_preview.py`), zonder dat er een Home Assistant-instantie nodig is.
- `dev/verify_knmi_mqtt.py <api-key>` — controleert de verbinding met KNMI's
  MQTT Notification Service en toont binnenkomende "nieuw bestand"-meldingen.
  Let op: hiervoor is een **eigen geregistreerde** API-sleutel nodig, de
  publieke anonieme demo-key (die de REST API wel accepteert) wordt voor MQTT
  geweigerd.

`tests/test_coordinator.py`, `tests/test_http.py` en `tests/test_init.py`
zijn opt-in: zet `GRIB_OVERLAY_SAMPLE_GRIB` op het pad van een echt
gedecodeerd GRIB-lead-time-bestand (zie `dev/render_preview.py`'s docstring
voor hoe je die krijgt) om ze mee te laten draaien; anders worden ze
overgeslagen.

## Architectuur / nieuwe bronnen toevoegen

Elke databron implementeert `custom_components/grib_overlay/sources/base.py`'s
`GribSource`-interface (dataset-catalogus, file listing, download) en wordt
geregistreerd in `sources/registry.py`. De rest van de integratie
(coordinator, decode/render-pipeline, HTTP-API, kaart-kaart) kent geen
KNMI-specifieke aannames buiten `sources/knmi.py` zelf.

## Licentie

[MIT](LICENSE)
