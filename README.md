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
- **Uitgebreid meteogram (alle parameters & bronnen).** Onderin elke waarde- en
  meteogram-popup staat de link **“Alle parameters & bronnen ▸”**. Die opent een
  Windy-achtig **tabel-meteogram**: één rij per parameter, gekleurde waarde-cellen
  en alle rijen op **dezelfde tijd-as** (kolommen). Het toont **alle beschikbare
  GRIB-data op dat punt uit álle geconfigureerde integraties** (KNMI, DWD, BSH …),
  per bron gegroepeerd; bronnen met een afwijkende tijdstap vullen simpelweg de
  bijbehorende kolommen (de rest blijft leeg). De cel-kleuren en eenheden volgen
  exact de in de card/integratie ingestelde **kleurschalen** (incl. eigen
  `color_scales`) en **eenheden** (`wind_unit`, `visibility_unit`,
  `direction_unit`); richtingen staan als **pijl én als getal** (kompas of 0–360°).
  **Tik een rijlabel** om die rij tijdelijk te verbergen (zodat je een beperkte
  set naast elkaar ziet); verborgen rijen komen terug via de chips bovenin of
  **“Alle rijen tonen”**. De standaard-selectie leg je vast met de card-optie
  [`meteogram_parameters`](#card-instellingen-lovelace-yaml). Met de keuze
  **“Kolommen”** bovenin (of de card-optie `meteogram_resolution`) kies je de
  tijdstap van de kolommen: **kwartier, uur, 3 uur of dag**. Bij kwartier/uur/
  3 uur wordt de **werkelijke waarde op dat tijdstip** getoond (geen gemiddelde);
  bij **dag** het **daggemiddelde** van alle data die dag (voor richting een
  vector-/kompasgemiddelde). **Neerslag** is hierop de uitzondering: die wordt per
  kolom **opgeteld** — de som over de periode die *eindigt* op die kolom (bv. de
  3-uurskolom `03` = neerslag van 01+02+03; de kolom `00` = 22+23 van de vorige
  dag plus 00), en bij dag de dagsom. Tijdens het samenstellen toont de popup een
  **laadindicator**; de data wordt per bron in **één verzoek** opgehaald
  (`point_all`-endpoint), zodat het openen snel blijft.
- **Modelvergelijking.** Een tweede card (`custom:grib-overlay-compare-card`) en
  een modus in het meteogram (**Weergave → “vergelijk modellen”**) laten zien wat
  de **verschillende GRIB-bronnen** op één punt voorspellen voor **één parameter**:
  een **lijngrafiek** met een lijn per model (Windy-achtig) plus een **tabel** met
  een rij per model (zelfde kwartier/uur/3 uur/dag-kolommen, kleuren en eenheden).
  In de aparte card kies je het punt op een **mini-kaart** (OpenStreetMap +
  OpenSeaMap) en vink je modellen in/uit. *(Een latere uitbreiding is het
  vergelijken met gemeten waarden en het bepalen van een delta.)*
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
   bewaarde forecast-runs (default 2), het poll-interval (default 30 minuten) en
   **eigen kleurschalen per parameter** (zie hieronder) aan.

### Eigen kleurschalen

In de integratie-opties kun je per parameter zelf bepalen tussen welke kleuren
de overlay interpoleert — zo maak je bijvoorbeeld zichtbaar welke windsnelheid je
nog acceptabel vindt en welke niet. Dit wordt **bij het renderen in de kaart
(PNG) gebakken** op volle resolutie, dus de legenda én de pijltjes volgen de
schaal automatisch.

Het veld **"Eigen kleurschalen"** neemt één parameter per regel:

```
wind_10m: 0:#2c7fb8, 8:#7fcdbb, 12:#ffffb2, 16:#fd8d3c, 24:#bd0026
temperature_2m: -10:#313695, 0:#ffffbf, 35:#a50026
```

- De **waarden staan in de eigen eenheid van de parameter** (m/s, °C, hPa, mm, m).
- Onder de laagste en boven de hoogste stop wordt de kleur vastgehouden.
- Een parameter zonder regel houdt de ingebouwde kleuren.
- Een wijziging **rendert de huidige run opnieuw** (op de achtergrond) zodat de
  nieuwe kleuren meteen doorkomen — dit is bedoeld als een instelling die je
  zelden aanpast.

## Cards toevoegen aan een dashboard

De integratie levert **twee** Lovelace-cards:

- **`custom:grib-overlay-card`** — de kaart met GRIB-overlay, tijd-slider/animatie
  en het uitgebreide meteogram (alle parameters van elke bron op een punt).
- **`custom:grib-overlay-compare-card`** — een **modelvergelijking**: kies één
  parameter en zie op een punt (klik op de mini-kaart) wat de verschillende
  GRIB-bronnen voorspellen, als **lijngrafiek + tabel** per model. Dezelfde
  vergelijking zit ook in het uitgebreide meteogram onder **Weergave → “vergelijk
  modellen”**.

### Overlay-card (`grib-overlay-card`)

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
# deeltjes-weergave (contrast t.o.v. de laag erachter):
# particle_color: "#0b1f3a"    # één vaste kleur i.p.v. velocity-kleuren (hoog contrast, bv. op mobiel)
# particle_width: 2            # lijndikte van de deeltjes (standaard 2)
# particle_base_opacity: 0.35  # hoe sterk de raster eronder gedimd wordt (0-1; standaard 0.35)
# isobaren-laag (alleen zinvol als de dataset luchtdruk heeft):
# show_isobars: true           # start met de isobaren+drukcentra-laag aan
# isobar_interval: 2           # hPa tussen de isobaren (standaard 4; kleiner = meer lijnen)
# isobar_levels: [1000, 1005, 1010]  # of: exact deze isobaren (overschrijft isobar_interval)
# isobar_smoothing: 60         # smoothing van het drukveld in km (standaard 60; 0 = uit; 100-150 = synoptischer)
# show_pressure_centres: false # H/L-drukcentra verbergen (standaard aan)
# pressure_prominence: 4       # hPa die een H/L moet "insluiten" om getoond te worden (standaard = isobar_interval)
# max_pressure_centres: 3      # hoogstens zoveel H én zoveel L tonen (standaard 4)
# center: [52.1, 5.3]
# zoom: 7
# grootte in een Secties-dashboard:
# columns: full   # breedte: "full" (volledig, standaard) of een getal kolommen
# rows: 8         # hoogte in grid-rijen
# eenheden (nautisch):
# wind_unit: kn        # wind + windstoten: m/s (standaard), kn, km/h of mph
# visibility_unit: NM  # zicht: km (standaard) of NM (zeemijlen)
# direction_unit: deg  # windrichting: compass (N/O/Z/W, standaard) of deg (0-360°)
# uitgebreid meteogram — standaard zichtbare rijen (rest start verborgen; leeg = alles):
# meteogram_parameters: [wind_10m, wind_gust_10m, temperature_2m, precipitation]
# meteogram_resolution: uur   # kolom-tijdstap: kwartier, uur, 3uur of dag (dag = gemiddeld; neerslag = som)
```

### Modelvergelijking-card (`grib-overlay-compare-card`)

Vergelijk op één punt wat de verschillende bronnen voorspellen. Klik op de
mini-kaart om het punt te verzetten; kies boven de parameter en de kolom-tijdstap.

```yaml
type: custom:grib-overlay-compare-card
parameter: wind_10m          # startparameter (union van alle bronnen)
center: [52.98, 4.12]        # startpositie van de mini-kaart (bv. een haven)
zoom: 9
# meteogram_resolution: 3uur # kolom-tijdstap van de tabel: kwartier, uur, 3uur of dag
# entries: [knmi, dwd]       # optioneel: alleen deze bronnen vergelijken
#                            #   (match op source, datasetsleutel/-naam, titel of entry-id)
# eenheden gelden net als bij de overlay-card:
# wind_unit: kn
# direction_unit: deg
```

De vergelijking toont **alle bronnen die de gekozen parameter hebben** als
gekleurde lijnen + een tabel (rij per model). Modellen die het punt niet dekken
(bv. BSH landinwaarts) worden onderaan als “niet getoond” benoemd. Vink modellen
in/uit met de selectievakjes onder de kaart.

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
  raster; **alleen voor wind**. Zie ze slecht tegen de laag erachter (vooral op
  mobiel)? Verhoog het contrast met `particle_color` (één vaste kleur i.p.v. de
  velocity-kleuren — bv. `#0b1f3a` donker of `#ffffff` wit), `particle_width`
  (dikkere lijnen) en/of `particle_base_opacity` (raster verder dimmen).
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
"ruis"-centra. Beperk ze verder met `max_pressure_centres` (standaard 4 per type)
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

## Alle instellingen — referentie

Volledige, exacte lijst van alle sleutels en waarden die je in de integratie
(config-flow/opties) en in de card-YAML kunt gebruiken. De sleutels zijn
hoofdlettergevoelig; gebruik ze exact zoals hieronder.

### Bronnen (`source`)

| `source` | Naam | API-sleutel |
| --- | --- | --- |
| `knmi` | KNMI Data Platform | ja (Open Data-sleutel) |
| `dwd` | DWD Open Data (golven) | nee |
| `bsh` | BSH (zeestroming Noordzee) | nee |

### Datasets (`dataset`)

| Bron | `dataset` | Naam | Grid | Horizon (max) | Stap |
| --- | --- | --- | --- | --- | --- |
| `knmi` | `harmonie_arome_cy43_p1` | HARMONIE-AROME Cy43 — Nederland | regulier lat/lon | 60 u | 1 u |
| `knmi` | `harmonie_arome_cy43_p3` | HARMONIE-AROME Cy43 — Europa (DINI) | rotated lat/lon | 60 u | 1 u |
| `dwd` | `ewam` | DWD EWAM — Europese golven | regulier lat/lon | 78 u | 1 u |
| `bsh` | `bsh_current_northsea` | BSH — Zeestroming Noordzee | regulier lat/lon | 48 u | 15 min |

### Parameters (`parameter` / `parameters`)

**KNMI** (`harmonie_arome_cy43_p1` en `harmonie_arome_cy43_p3`, identiek):

| `parameter` | Naam | Eenheid | Type |
| --- | --- | --- | --- |
| `wind_10m` | Wind (10m) | m/s | vector |
| `wind_gust_10m` | Windstoten (10m) | m/s | vector |
| `temperature_2m` | Temperatuur (2m) | °C | scalar |
| `dewpoint_2m` | Dauwpunt (2m) | °C | scalar |
| `humidity_2m` | Relatieve luchtvochtigheid (2m) | % | scalar |
| `precipitation` | Neerslag | mm | scalar |
| `pressure_msl` | Luchtdruk (zeeniveau) | hPa | scalar |
| `visibility` | Zicht | km | scalar |
| `cloud_cover` | Bewolking | % | scalar |

**DWD** (`ewam`):

| `parameter` | Naam | Eenheid | Type |
| --- | --- | --- | --- |
| `wave_height` | Golfhoogte (significant) | m | scalar |
| `wave_period` | Golfperiode (gemiddeld) | s | scalar |
| `wave_direction` | Golfrichting (gemiddeld) | ° | scalar |

**BSH** (`bsh_current_northsea`):

| `parameter` | Naam | Eenheid | Type |
| --- | --- | --- | --- |
| `current` | Zeestroming (oppervlak) | m/s | vector |

Het **type** bepaalt welke weergaven beschikbaar zijn: `vector`-parameters
(`wind_10m`, `wind_gust_10m`, `current`) ondersteunen `particles`/`vectors`; een
richting-parameter (eenheid °, dus `wave_direction`) schakelt `wavevectors` in;
en `pressure_msl` (eenheid hPa) schakelt de isobaren-laag in.

### Integratie: setup-velden (config-flow)

| Sleutel | Waarden |
| --- | --- |
| `source` | `knmi`, `dwd` of `bsh` |
| `api_key` | KNMI Open Data-sleutel (leeg laten voor DWD/BSH) |
| `notification_api_key` | optioneel; KNMI push-sleutel (leeg = alleen pollen) |
| `dataset` | een dataset-sleutel uit de tabel hierboven |
| `parameters` | lijst van parameter-sleutels die je wilt bijhouden |

### Integratie: opties (Configureren)

| Sleutel | Type | Default | Bereik / vorm |
| --- | --- | --- | --- |
| `forecast_horizon_hours` | getal (uren) | `24` | 1–60 |
| `retain_runs` | geheel getal | `2` | 1–10 |
| `update_interval_minutes` | geheel getal (min) | `30` | 5–180 |
| `notification_api_key` | tekst | (leeg) | KNMI push-sleutel |
| `color_scales` | meerregelige tekst | (leeg) | per regel: `parameter: waarde:#hex, waarde:#hex, …` (waarden in de **eigen eenheid** van de parameter) |

### Card-instellingen (Lovelace-YAML)

| Sleutel | Type | Default | Waarden / betekenis |
| --- | --- | --- | --- |
| `dataset` | tekst | (eerste) | datasetsleutel, -naam of titel — welke dataset bij het laden |
| `entry_id` | tekst | (eerste) | exacte config-entry-id (wint van `dataset`) |
| `parameter` | tekst | (eerste) | parametersleutel — welke parameter bij het laden |
| `render_mode` | tekst | `raster` | `raster`, `particles`, `vectors`, `wavevectors` (valt terug op `raster` als de parameter het niet ondersteunt) |
| `arrow_halo_color` | hex-kleur | `#ffffff` | contour (halo) om de wind-pijlen |
| `particle_color` | hex-kleur | (velocity-kleuren) | één vaste deeltjeskleur voor hoog contrast |
| `particle_width` | getal | `2` | lijndikte van de deeltjes |
| `particle_base_opacity` | getal `0`–`1` | `0.35` | dimming van de raster onder de deeltjes |
| `show_isobars` | bool | `false` | isobaren + H/L-drukcentra als aparte laag |
| `isobar_interval` | getal (hPa) | `4` | afstand tussen isobaren |
| `isobar_levels` | lijst getallen (hPa) | — | exacte isobaren (overschrijft `isobar_interval`) |
| `isobar_smoothing` | getal (km) | `60` | gladstrijken drukveld (`0` = uit) |
| `show_pressure_centres` | bool | `true` | H/L-drukcentra tonen |
| `pressure_prominence` | getal (hPa) | = `isobar_interval` | insluit-drempel voor een H/L |
| `max_pressure_centres` | geheel getal | `4` | max. aantal H én L |
| `center` | `[lat, lon]` | `[52.1, 5.3]` | startpositie van de kaart |
| `zoom` | getal | `7` | start-zoomniveau |
| `columns` | `full` of getal | `full` | breedte in een Secties-dashboard |
| `rows` | getal | — | hoogte in grid-rijen (masonry) / begingrootte |
| `grid_options` | object | — | HA-eigen `{rows, columns}` (wint van `rows`/`columns`) |
| `wind_unit` | tekst | `m/s` | `m/s`, `kn`, `km/h`, `mph` |
| `visibility_unit` | tekst | `km` | `km`, `NM` |
| `direction_unit` | tekst | `compass` | `compass`, `deg` |
| `meteogram_parameters` | lijst of tekst | — | parametersleutels die in het uitgebreide meteogram **standaard zichtbaar** zijn; de rest start verborgen (in te schakelen via de chips). Leeg = alle rijen tonen. Match op parametersleutel, dus geldt voor álle bronnen |
| `meteogram_resolution` | tekst | `uur` | tijdstap van de meteogram-kolommen: `kwartier`, `uur`, `3uur` of `dag`. Bij `dag` het daggemiddelde (neerslag: dagsom); fijner = waarde op dat tijdstip. In het venster zelf ook via “Kolommen” te wisselen |

De oude schrijfwijze `renderMode` (camelCase) blijft ook werken naast
`render_mode`. `meteogram_parameters` mag zowel een YAML-lijst als een door
komma’s/spaties gescheiden tekst zijn; bv. `[wind_10m, wind_gust_10m,
temperature_2m]` of `"wind_10m, wind_gust_10m, temperature_2m"`. De verborgen/
zichtbare keuze die je daarná in het meteogram zelf maakt (rijlabel tikken,
chips, “Alle rijen tonen”) geldt tijdelijk, voor dat geopende venster.

### Modelvergelijking-card (`grib-overlay-compare-card`)

| Sleutel | Type | Default | Waarden / betekenis |
| --- | --- | --- | --- |
| `parameter` | tekst | (eerste) | startparameter die vergeleken wordt (union van alle bronnen) |
| `center` | `[lat, lon]` | `[52.1, 5.3]` | startpositie van de mini-kaart |
| `zoom` | getal | `7` | start-zoomniveau van de mini-kaart |
| `entries` (of `models`) | lijst of tekst | — | alleen deze bronnen vergelijken; match op `source`, datasetsleutel/-naam, titel of entry-id. Leeg = alle bronnen die de parameter hebben |
| `meteogram_resolution` | tekst | `uur` | kolom-tijdstap van de tabel: `kwartier`, `uur`, `3uur`, `dag` |
| `wind_unit`, `visibility_unit`, `direction_unit` | tekst | zie hieronder | zelfde eenheden-opties als de overlay-card |

### Eenheden (geldige waarden + aliassen)

- **`wind_unit`** — geldt voor alle m/s-parameters (wind, windstoten,
  zeestroming): `m/s` (standaard), `kn` (knopen; ook `kt`, `kts`, `knots`,
  `knopen`, `knoop`), `km/h` (ook `km/u`, `kmh`, `kph`), `mph`.
- **`visibility_unit`** — geldt voor `visibility`: `km` (standaard), `NM`
  (zeemijlen; ook `nm`, `zeemijl`, `zeemijlen`).
- **`direction_unit`** — windrichting in de readout en op de meteogram-as:
  `compass` (kompas `N/O/Z/W`, standaard), `deg` (`0–360°`; ook `degrees`,
  `graden`, `360`, `0-360`, `°`).

Eenheden zijn puur een weergavekeuze in de card (de onderliggende data en de
kleurschaal veranderen niet; alleen de legenda-getallen en labels).

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
