# GRIB Weather Overlay voor Home Assistant

Toont GRIB-weerdata (wind, neerslag, temperatuur, druk, zicht, bewolking, ...)
als kleurenlaag over een [OpenSeaMap](https://map.openseamap.org)-kaart in
Home Assistant. Je kiest een tijdstip via een slider, of een begin/eind/stap
om een animatie van de voorspelling af te spelen.

Databronnen (via een `GribSource`-interface, zodat bronnen toegevoegd kunnen
worden zonder de kaart of de rest van de backend te wijzigen):

- [KNMI Data Platform](https://dataplatform.knmi.nl/) — HARMONIE-AROME
  (Nederland en Europa/DINI), GRIB1. Vereist een gratis Open Data-sleutel.
- [DWD Open Data](https://opendata.dwd.de/) — het **EWAM golfmodel** voor de
  Europese zeeën (significante golfhoogte, gemiddelde golfrichting en -periode),
  GRIB2, **zonder sleutel**.
- [BSH](https://www.bsh.de/) — **zeestroming** (oppervlakte-u/v) voor de hele
  Noordzee incl. de Nederlandse, Belgische en noord-Franse kust, 15-minuten-
  stappen, GRIB1, **zonder sleutel** (open FTP).

## Features

- Configureerbare parameters: wind (10m), windstoten, temperatuur (2m),
  dauwpunt (2m), relatieve luchtvochtigheid (2m), neerslag, luchtdruk
  (zeeniveau), zicht, bewolking.
- **Golven** (DWD EWAM): significante golfhoogte, gemiddelde golfrichting en
  golfperiode als kleurlaag over de Europese zeeën — met meteogram en
  waarde-onder-de-muis, net als de andere parameters.
- **Zeestroming** (BSH): oppervlakte-stroming (snelheid + richting) voor de
  Noordzee als kleurlaag met deeltjes/pijlen — zoals wind, maar dan het water.
  15-minuten-resolutie, dus fijne getijdetails.
- Eén-tijdstip-slider én een animatiemodus (begin, eind, stap, afspeelsnelheid).
- **Windy.com-stijl geanimeerde deeltjes voor wind** (via de meegeleverde
  `leaflet-velocity`), naast de gekleurde raster-overlay. Kies "Wind (deeltjes)"
  in de kaart bij een wind-parameter; de deeltjes stromen mee met de
  windrichting boven een gedimde snelheidskaart. Er is ook een
  **"Wind (vectoren)"**-modus met pijltjes (richting + grootte); de pijlen zijn
  **gekleurd naar windsnelheid** (dezelfde kleuren als de raster-legenda) met een
  witte contour, zodat ze contrast houden met de overlay.
- **Isobaren + drukcentra** als aparte laag: zet het vinkje **"Isobaren"** aan
  en er komen drukcontourlijnen om de 4 hPa (de ronde 20 hPa-lijnen dikker) met
  waarde-labels bovenop, plus **H**oge- (blauw) en **L**agedrukcentra (rood) met
  hun kerndruk. Dit legt zich **over elke andere overlay van dezelfde dataset**
  (bv. wind + isobaren), zolang die dataset een luchtdruk-parameter heeft. De
  druk wordt uit de druk-parameter van diezelfde integratie gehaald.
  *(Fronten/occlusies worden door analisten getekend en zitten niet in de open
  GRIB-data; die staan er bewust nog niet bij.)*
- **Waarde onder de muis** (voor álle parameters) wordt live linksonder in de
  kaart getoond, in de ingestelde eenheden; voor wind ook de richting. **Klik/
  tik** zet de waarde vast in een popup, en **houd ingedrukt / rechtsklik**
  opent een wegklikbaar **meteogram** (waarde-over-tijd op dat punt) met major
  gridlijnen en minor ticks op beide assen. Bij **wind** worden **wind én
  windstoten samen** getekend op dezelfde snelheidsas — met een vlaag-envelop
  (band tussen wind en stoot) — en op de **tweede y-as** zowel de **wind- als de
  windstoot-richting** (kompas N/O/Z/W). Windstoten moeten daarvoor als parameter
  aan staan.
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
  wat voor reden dan ook niet lukt. Je gewone Open Data API-sleutel werkt
  hiervoor; een aparte Notification Service-sleutel is niet nodig.

## Vereisten

- Home Assistant OS of Supervised. Alle dependencies zijn pure-Python /
  universele wheels (`numpy`, `Pillow`, `paho-mqtt`); zowel GRIB1 (KNMI) als
  GRIB2 (DWD EWAM, simple packing) worden door een meegeleverde eigen decoder
  gelezen, dus er is géén `eccodes`/`cfgrib`
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
2. Kies de bron. Voor **KNMI Data Platform** vul je je Open Data API-sleutel in
   (die wordt ook voor de push-notificaties/MQTT gebruikt; het optionele
   **Notification Service API-sleutel**-veld kun je leeg laten). Voor **DWD Open
   Data (golven)** laat je de sleutel-velden leeg — DWD heeft geen sleutel nodig.
3. Kies een dataset. KNMI: HARMONIE-AROME Cy43 **Nederland** (standaard) of
   **Europa (DINI)**. DWD: **EWAM** (Europese golven). Wil je zowel weer als
   golven, voeg dan twee integratie-instanties toe (één per bron); in de kaart
   wissel je tussen instanties.
4. Kies welke parameters bijgehouden moeten worden.
5. Optioneel: pas via de integratie-opties de voorspellingshorizon (default
   24 uur, max 60 uur — zo ver reikt de KNMI HARMONIE-voorspelling), het aantal
   bewaarde forecast-runs (default 2) en het poll-interval (default 30 minuten)
   aan.

## Kaart toevoegen aan een dashboard

Voeg een kaart van het type `custom:grib-overlay-card` toe, bijvoorbeeld via
de YAML-editor van een dashboard:

```yaml
type: custom:grib-overlay-card
# optioneel: vast een specifieke dataset/parameter kiezen bij het laden
# dataset: bsh_current_northsea   # datasetsleutel, -naam of de titel uit de keuzelijst
# entry_id: <config entry id>     # exacte config-entry (wint van dataset)
# parameter: wind_10m
# render_mode: vectors  # startweergave: raster (standaard), particles, vectors of wavevectors
# arrow_halo_color: "#ffffff"  # kleur van de contour (halo) om de wind-pijlen (standaard wit)
# isobaren-laag (alleen zinvol als de dataset luchtdruk heeft):
# show_isobars: true           # start met de isobaren+drukcentra-laag aan
# isobar_interval: 2           # hPa tussen de isobaren (standaard 4; kleiner = meer lijnen)
# isobar_levels: [1000, 1005, 1010]  # of: exact deze isobaren (overschrijft isobar_interval)
# isobar_smoothing: 60         # smoothing van het drukveld in km (standaard 60; 0 = uit; 100-150 = synoptischer)
# show_pressure_centres: false # H/L-drukcentra verbergen (standaard aan)
# pressure_prominence: 4       # hPa die een H/L moet "insluiten" om getoond te worden (standaard = isobar_interval)
# max_pressure_centres: 3      # hoogstens zoveel H én zoveel L tonen (standaard 3)
# center: [52.1, 5.3]
# zoom: 7
# grootte in een Secties-dashboard:
# columns: full   # breedte: "full" (volledig, standaard) of een getal kolommen
# rows: 8         # hoogte in grid-rijen
# eenheden (nautisch):
# wind_unit: kn        # wind + windstoten: m/s (standaard), kn, km/h of mph
# visibility_unit: NM  # zicht: km (standaard) of NM (zeemijlen)
# direction_unit: deg  # windrichting: compass (N/O/Z/W, standaard) of deg (0-360°)
```

Met `dataset` kies je welke dataset de kaart bij het laden standaard toont;
de waarde mag de datasetsleutel zijn (bv. `bsh_current_northsea`), de
datasetnaam, of de titel zoals die in de keuzelijst van de kaart staat
(hoofdletterongevoelig). Wil je in plaats daarvan een exacte config-instantie
vastzetten, gebruik dan `entry_id` (die wint van `dataset`). Zonder
`dataset`/`entry_id`/`parameter` pakt de kaart automatisch de eerst
geconfigureerde dataset en het eerste geselecteerde parametertype, en kun je
in de kaart zelf wisselen.

**`render_mode` — startweergave.** Bepaalt met welke weergave de kaart opent
(je kunt in de kaart altijd wisselen via de weergave-keuzelijst). Keuzes:

- `raster` — gekleurde vlakvulling van de parameter (**standaard**).
- `particles` — windy.com-achtige geanimeerde deeltjes boven een gedimde
  raster; **alleen voor wind**.
- `vectors` — pijltjes (richting + grootte), gekleurd naar windsnelheid met een
  contour; **alleen voor wind**.
- `wavevectors` — pijltjes voor de golfrichting; **alleen voor golven**.

Past de gekozen modus niet bij de parameter (bijv. `vectors` terwijl er geen
wind is), dan valt de kaart automatisch terug op `raster`. De contourkleur van
de wind-pijlen stel je in met `arrow_halo_color` (standaard wit).

**Isobaren-laag.** `show_isobars: true` opent met de isobaren + H/L-drukcentra
als **aparte laag** bovenop de gekozen weergave (dus niet een `render_mode`;
in de kaart is dit het vinkje *Isobaren*). Deze laag verschijnt alleen als de
dataset een luchtdruk-parameter heeft. Regel welke isobaren getekend worden met
`isobar_interval` (hPa tussen de lijnen, standaard 4) of `isobar_levels` (een
lijst met exacte hPa-waarden). Met `isobar_smoothing` (km, standaard 60) strijk
je het drukveld glad tot synoptische schaal — dat geeft nettere isobaren én
betrouwbaardere H/L; hetzelfde gladgestreken veld voedt beide, dus ze blijven
consistent (0 = niet gladstrijken, 100–150 = synoptischer).

De **H/L-drukcentra** worden bepaald zoals op een echte weerkaart: een centrum
wordt alleen getoond als het door minstens één gesloten isobaar wordt omsloten
(instelbaar met `pressure_prominence`, standaard gelijk aan `isobar_interval`),
plus een minimale onderlinge afstand en een maximum. Zo verdwijnen de vele kleine
"ruis"-centra. Beperk ze verder met `max_pressure_centres` (standaard 3 per type)
of zet ze uit met `show_pressure_centres: false`.

### Grootte / layout

In een **Secties-dashboard** vult de kaart standaard de volledige breedte en
past de kaarthoogte zich aan de toegewezen cel aan. De hoogte/breedte in een
Secties-dashboard bepaal je op de HA-manier:

- **Slepen** aan de handvatten op de rand van de kaart in de dashboard-editor
  (de betrouwbaarste manier), of
- **In YAML met HA's eigen `grid_options`**:
  ```yaml
  type: custom:grib-overlay-card
  grid_options:
    rows: 10       # hoogte in grid-rijen
    columns: full  # of een aantal kolommen
  ```
  Let op: de losse `rows:`/`columns:` van de kaart zelf gelden alleen als
  *begingrootte* en worden door HA overschreven zodra er een `grid_options`
  is opgeslagen (dat gebeurt zodra je de kaart plaatst of sleept). Gebruik in
  een Secties-dashboard dus `grid_options` of de sleep-handvatten.

In een gewoon (**masonry**) dashboard bepaalt de losse `rows:` van de kaart de
kaarthoogte.

### Eenheden

Voor nautisch gebruik kun je in de kaart optioneel andere eenheden tonen. Dit
is puur een weergavekeuze in de kaart (de onderliggende data verandert niet):

- `wind_unit`: eenheid voor wind én windstoten — `m/s` (standaard), `kn`
  (knopen / zeemijlen per uur), `km/h` of `mph`.
- `visibility_unit`: eenheid voor zicht — `km` (standaard) of `NM` (zeemijlen).
- `direction_unit`: weergave van de windrichting (in de readout onder de muis en
  op de tweede as van het wind-meteogram) — `compass` (kompas `N/O/Z/W`,
  standaard) of `deg` (numeriek `0–360°`).

De legenda en het label in de parameterkeuze worden dan automatisch omgerekend.

## Back-ups

De integratie cachet zijn werkbestanden onder `/config/grib_overlay/…`, en Home
Assistant neemt heel `/config` mee in een back-up. Omdat de integratie continu
nieuwe GRIB-bestanden downloadt en oude weggooit, kan een bestand precies tussen
"back-up inventariseert" en "back-up schrijft" verdwijnen — dan faalde vroeger de
héle back-up met `FileNotFoundError`. Dat is nu opgelost:

- **Pauze tijdens de back-up.** Via HA's back-up-platform (`async_pre_backup` /
  `async_post_backup`) pauzeert de integratie het verwerken en opruimen van runs
  zolang een back-up loopt; een lopende verwerking wordt eerst netjes afgerond
  vóór het archiveren begint. De eerstvolgende poll ná de back-up pakt een nieuwe
  run alsnog op. Dit gebruikt hetzelfde mechanisme als de recorder en vereist
  HA's back-up-systeem van **2025.1+** (zowel core- als HAOS-back-ups).
- **Ruwe downloads buiten de back-up.** Losse per-bestand-bronnen (BSH, DWD)
  downloaden hun ruwe GRIB-bestanden naar `/tmp` (buiten `/config`), zodat die
  transiënte bestanden sowieso nooit in een back-up belanden. De grote
  KNMI-tar (~850MB) blijft op schijf onder `/config` — in RAM (`/tmp` is vaak
  tmpfs) zou die te groot zijn — en wordt door de pauze hierboven beschermd.

## Bekende beperkingen

- Eén HARMONIE-forecast-run bij KNMI is een tar-archief van ~850MB (alle
  lead times samen). Er is geen API om losse lead times te downloaden, dus
  een **nieuwe** run kost die volledige download (een paar minuten); alleen de
  lead times binnen de ingestelde voorspellingshorizon worden gedecodeerd en
  als PNG bewaard, de rest wordt direct weer verwijderd. Zet de horizon niet
  hoger dan nodig. Bij een **herstart** wordt de al-verwerkte run van schijf
  hergebruikt (geen nieuwe download), en de eventuele download van een nieuwere
  run gebeurt op de achtergrond — de integratie is meteen na de start
  beschikbaar met de reeds gecachte beelden.
- Ondersteunde datasets: `harmonie_arome_cy43_p1` (Nederland, regular lat-lon)
  en `harmonie_arome_cy43_p3` (Europa/DINI-domein, deterministisch). Die laatste
  staat op een **rotated lat-lon grid** en wordt bij het decoderen naar een
  regulier geografisch grid geprojecteerd (inclusief het meedraaien van de
  wind-u/v-componenten naar echt noord/oost). Het Europa-domein is groter, dus
  download en verwerking kosten meer tijd/geheugen dan Nederland — zet de
  voorspellingshorizon niet hoger dan nodig.
- De **ensemble**-variant `harmonie_arome_cy43_p4a` (EPS) wordt nog niet
  ondersteund; die vereist een keuze/aggregatie over de ensembleleden.
- Van **DWD Open Data** wordt (voorlopig) alleen het **EWAM golfmodel**
  ondersteund. EWAM gebruikt eenvoudige GRIB2-packing en is dus zonder binaire
  library te lezen; andere DWD-modellen (bijv. ICON-EU) gebruiken vaak
  CCSDS/AEC- of JPEG2000-compressie, wat wél zo'n library zou vereisen.
- **BSH-zeestroming** is 15-minuten-data: één BSH-bestand bevat een heel etmaal
  aan tijdstappen (96 per 24 u). De integratie splitst dat in losse tijdstappen,
  maar houd er rekening mee dat een langere voorspellingshorizon veel frames
  oplevert (24 u = 96 frames). Alleen het BSH-Noordzee-gebied wordt ondersteund
  (dat dekt de NL/BE/FR-kust); de fijnere deelgebieden en de Oostzee nog niet.

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
