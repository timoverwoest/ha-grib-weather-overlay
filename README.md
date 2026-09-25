# GRIB Weather Overlay voor Home Assistant

> **Taal / Language:** 🇳🇱 Nederlands (hieronder) · 🇬🇧 [English documentation](#grib-weather-overlay-for-home-assistant--english) (onderaan deze pagina)

Toont GRIB-weerdata (wind, neerslag, temperatuur, druk, zicht, bewolking, ...)
als kleurenlaag over een [OpenSeaMap](https://map.openseamap.org)-kaart in
Home Assistant. Je kiest een tijdstip via een slider, of een begin/eind/stap
om een animatie van de voorspelling af te spelen.

Databronnen (via een `GribSource`-interface, zodat bronnen toegevoegd kunnen
worden zonder de kaart of de rest van de backend te wijzigen):

- [KNMI Data Platform](https://dataplatform.knmi.nl/) — HARMONIE-AROME
  (Nederland en Europa/DINI), GRIB1. Vereist een gratis Open Data-sleutel.
- [DWD Open Data](https://opendata.dwd.de/) — de golfmodellen **EWAM** (Europese
  zeeën) en **GWAM** (wereldwijd, tot +174 uur) met golfhoogte, deining en
  windgolven inclusief richting en periode, plus het **ICON-D2 weermodel**
  (2,2 km, heel Nederland en de zuidelijke Noordzee), GRIB2, **zonder sleutel**.
- [BSH](https://www.bsh.de/) — **zeestroming** (oppervlakte-u/v) voor de hele
  Noordzee incl. de Nederlandse, Belgische en noord-Franse kust, 15-minuten-
  stappen, GRIB1, **zonder sleutel** (open FTP).
- [DMI](https://www.dmi.dk/friedata) — het Deense golfmodel **WAM**
  (Noordzee/Oostzee op ~5 km en de Noord-Atlantische Oceaan op 0,25°) en het
  stormvloedmodel **DKSS** (stroming, waterstand en watertemperatuur van
  Skagerrak tot het Kanaal), tot 5 dagen vooruit, GRIB1, **zonder sleutel**.
- [Rijkswaterstaat](https://noos.matroos.rws.nl/) (NOOS-Matroos) — het
  **DCSM-model** (waterstand en stroming van de Noorse kust tot Noord-Spanje,
  en het fijnere **ZUNO-nest** voor de zuidelijke Noordzee) en de
  **SWAN-golfmodellen** (Noordzee, en fijnmazig langs de Nederlandse kust),
  48 uur vooruit, NetCDF, **zonder sleutel**.
- [MET Norway](https://api.met.no/weatherapi/gribfiles/1.1/documentation) — weer
  (MEPS), golven (4 km) en stroming (800 m-model) voor **Oslofjord, Skagerrak en
  Sørlandet**, 3 tot 5 dagen vooruit, GRIB1, **zonder sleutel**.
- [NOAA](https://nomads.ncep.noaa.gov/) (NCEP NOMADS) — het wereldmodel **GFS**
  en het golfmodel **GFS-Wave**, allebei tot **+384 uur** op 0,25°: het enige
  model hier dat verder dan een paar dagen kijkt, GRIB2, **zonder sleutel**.

## Inhoud

- [Features](#features)
- [Bronnen en datasets](#bronnen-en-datasets)
  - [Waar kies ik uit?](#waar-kies-ik-uit)
  - [KNMI Data Platform (`knmi`) — sleutel nodig](#knmi-data-platform-knmi--sleutel-nodig)
  - [DWD Open Data (`dwd`) — geen sleutel](#dwd-open-data-dwd--geen-sleutel)
  - [NOAA (`noaa`) — geen sleutel](#noaa-noaa--geen-sleutel)
  - [Rijkswaterstaat (`rws`) — geen sleutel](#rijkswaterstaat-rws--geen-sleutel)
  - [DMI Open Data (`dmi`) — geen sleutel](#dmi-open-data-dmi--geen-sleutel)
  - [BSH (`bsh`) — geen sleutel](#bsh-bsh--geen-sleutel)
  - [MET Norway (`metno`) — geen sleutel](#met-norway-metno--geen-sleutel)
- [Vereisten](#vereisten)
- [Installatie](#installatie)
- [Configuratie](#configuratie)
- [Cards toevoegen aan een dashboard](#cards-toevoegen-aan-een-dashboard)
- [Vier voorbeeld-cards](#vier-voorbeeld-cards)
- [Alle instellingen — referentie](#alle-instellingen--referentie)
  - [Bronnen (`source`)](#bronnen-source)
  - [Datasets (`dataset`)](#datasets-dataset)
  - [Parameters (`parameter` / `parameters`)](#parameters-parameter--parameters)
  - [Integratie: setup-velden (config-flow)](#integratie-setup-velden-config-flow)
  - [Integratie: opties (Configureren)](#integratie-opties-configureren)
  - [Card-instellingen (Lovelace-YAML)](#card-instellingen-lovelace-yaml)
  - [Modelvergelijking-card (`grib-overlay-compare-card`)](#modelvergelijking-card-grib-overlay-compare-card-1)
  - [Weerkaart-card (`grib-overlay-weathermap-card`)](#weerkaart-card-grib-overlay-weathermap-card-1)
  - [Eenheden (geldige waarden + aliassen)](#eenheden-geldige-waarden--aliassen)
  - [Kaartlagen](#kaartlagen)
- [Prestaties](#prestaties)
- [Sleutels & problemen oplossen](#sleutels--problemen-oplossen)
- [Taal](#taal)
- [Back-ups](#back-ups)
- [Bekende beperkingen](#bekende-beperkingen)
- [Ontwikkelen & testen](#ontwikkelen--testen)
- [Architectuur / nieuwe bronnen toevoegen](#architectuur--nieuwe-bronnen-toevoegen)
- [Licentie](#licentie)

## Features

- Configureerbare parameters: wind (10m), windstoten, temperatuur (2m),
  dauwpunt (2m), relatieve luchtvochtigheid (2m), neerslag, luchtdruk
  (zeeniveau), zicht, bewolking.
- **Golven** (DWD EWAM): significante golfhoogte, gemiddelde golfrichting en
  golfperiode als kleurlaag over de Europese zeeën — met meteogram en
  waarde-onder-de-muis, net als de andere parameters.
- **Deining en windgolven** (DWD EWAM) apart: hoogte, richting, gemiddelde
  periode en piekperiode van elk. De richtingspijlen volgen de gekozen soort:
  kijk je naar deining, dan wijzen de pijlen de deiningsrichting aan.
- **Tweede fijnmazig weermodel** (DWD ICON-D2, 2,2 km): dezelfde parameters als
  KNMI HARMONIE plus **CAPE** (energie voor onweer), elke 3 uur een nieuwe run
  tot +48 uur. Omdat de parameters dezelfde sleutels hebben, leg je beide
  modellen direct naast elkaar in de modelvergelijking.
- **Zeestroming** (BSH): oppervlakte-stroming (snelheid + richting) voor de
  Noordzee als kleurlaag met deeltjes/pijlen — zoals wind, maar dan het water.
  15-minuten-resolutie, dus fijne getijdetails.
- **Golven, stroming en waterstand tot 5 dagen vooruit** (DMI): WAM-golven van
  de Oslofjord tot Noord-Spanje, en stroming, waterstand en watertemperatuur
  van Skagerrak tot het Kanaal.
- **Waterstand en stroming van Rijkswaterstaat** (DCSM) van de Noorse kust tot
  Noord-Spanje, en golven van de Noordzee en fijnmazig langs de Nederlandse kust
  (SWAN) — dezelfde modellen die Rijkswaterstaat zelf gebruikt.
- **De Noorse kant** (MET Norway): wind, neerslag, luchtdruk, golven en stroming
  tot in de Oslofjord.
- **Ver vooruit kijken** (NOAA GFS en GFS-Wave, tot +384 uur): waar HARMONIE,
  ICON-D2 en EWAM na twee of drie dagen ophouden, loopt GFS door tot zestien
  dagen. Grof (0,25°), dus geen vervanging van de fijne modellen maar de
  aanvulling erop — en dankzij server-side uitsnede kost een tijdstap maar
  tientallen kilobytes.
- **Golven voor de Atlantische aanloop** (DWD GWAM, tot +174 uur): dezelfde
  velden als EWAM, maar wereldwijd en meer dan twee keer zo ver vooruit — voor
  deining die nog dagen onderweg is.
- **KNMI-weerkaart met fronten** als eigen card: analyses en verwachtingskaarten
  tot 48 uur vooruit.
- **Per card kiezen welke datasets erin zitten** (`datasets` / `parameters` en
  hun `exclude_`-varianten): zet de golven op hun eigen card en houd de
  weerkaart schoon — het filter geldt ook voor het uitgebreide meteogram.
- **Zeekaartlagen** zoals op map.openseamap.org: zeetekens, sport, dieptelijnen,
  dieptemetingen, GEBCO-diepte en een EMODnet-dieptekaart als ondergrond, via een
  lagenknop op de kaart.
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
- **Waarde-aanwijzer op elke grafiek.** Ga met de **muis over** een grafiek (of
  **tik/sleep met je vinger**) en er verschijnt een verticale peillijn met een
  tooltip die het **tijdstip (x)** en de **waarde(n) (y)** op dat punt toont — in
  het meteogram, in de modelvergelijking en in de vergelijk-modus. Bij meerdere
  lijnen staat elk model met zijn eigen waarde in de tooltip.
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
  OpenSeaMap) en vink je modellen in/uit. Het **gekozen punt wordt gedeeld** met
  de gewone overlay-card en omgekeerd (klik in de een, de ander neemt het over).
- **Meting & delta.** Zet in de vergelijking **“Meting invoeren”** aan om per
  kolom een **gemeten waarde** in te typen. De meting verschijnt als donkere lijn
  in de grafiek en als rij in de tabel, en per model komt er een **Δ-rij**
  (**meting − model**; `+` = meting hoger dan de bron) bij met een samenvatting:
  **bias, MAE en RMSE**. Zo zie je
  direct welk model het dichtst bij de werkelijkheid zit. Ingevoerde metingen
  worden **bewaard per punt + parameter** (in `localStorage`, dus ze blijven staan
  na herladen en zijn in elke card-weergave beschikbaar): het punt krijgt een
  **oranje speld** op **elke** kaart (overlay- én vergelijk-card), en klik je die
  aan dan opent het punt mét de opgeslagen waarden weer — ook in het meteogram van
  de overlay-card (Weergave → vergelijk modellen). Met **“Wis meting”** verwijder
  je de opgeslagen meting van het punt in één klik (de speld verdwijnt overal), en
  met **“Wis alle meetdata”** gooi je in één keer de metingen van **alle** punten
  weg (met bevestiging, en met het aantal punten op de knop) — handig op de
  telefoon, waar je een punt alleen kwijtraakt door naar een ánder punt te gaan
  en het laatste punt dus blijft staan.
- **Meetstations in de buurt + downloaden.** Zodra “Meting invoeren” aanstaat
  verschijnen de **meetstations binnen een instelbare straal** (standaard **10 km**,
  via `measurement_radius_km` of het straal-veld) rond het punt: als **groene stippen
  op de mini-kaart** én als **knoppen** (met afstand) onder de tabel. Alleen stations
  die **daadwerkelijk data hebben voor de gekozen parameter** worden getoond (de
  integratie vraagt dit vooraf op bij KNMI/RWS), en voor **water/golven/stroming**
  komen de stations van **RWS**, voor weer van **KNMI**. **Klik een station** (of de
  knop **“Meetstation downloaden”**) om de **werkelijke waarnemingen op te halen** en
  als meting te tonen — precies zoals handmatige meetwaarden (bewaard per punt +
  parameter, met een oranje speld). Geeft een station tóch geen data terug, dan wordt
  het meteen verborgen. *(De koppeling met de echte KNMI/RWS-API's is best-effort en
  moet je op je eigen HAOS met je KNMI-sleutel verifiëren; zie “Metingen automatisch
  ophalen”.)*
- **Absolute én relatieve delta.** De Δ-rijen tonen per kolom zowel de **absolute**
  afwijking (**meting − model**, `+` = meting hoger dan de bron) als de **relatieve**
  (%, t.o.v. de bronwaarde). De samenvatting geeft bias (abs + %), MAE en RMSE per model.
- **Gecorreleerde (gecorrigeerde) voorspelling.** Kies bij **“Correctie”** *absoluut*
  (verschuiven) of *relatief* (schalen) en vink aan **op welke bronnen** je het
  toepast. Elke aangevinkte bron krijgt dan een **gecorrigeerde lijn/rij**: zijn
  eigen gemiddelde afwijking t.o.v. de meting over de overlappende (verleden)
  kolommen, vooruit doorgetrokken op de hele voorspelling — zodat je een op de
  meting bijgestelde voorspelling ziet (stippellijn in de grafiek). Was de meting
  gemiddeld **hoger** dan de bron, dan gaat de correctie **omhoog** (en omgekeerd).
- **Gedeelde klikpositie.** De aangeklikte positie wordt gedeeld tussen de
  overlay-card en de vergelijk-card (ook tussen dashboardpagina's, voor de sessie).
  In de overlay-card opent op die positie meteen het **waarde-venster** (en sluit
  het vorige).
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
  wat voor reden dan ook niet lukt. Hiervoor is een **aparte Notification
  Service-sleutel** nodig; die service autoriseert los van Open Data en weigert
  een Open Data-sleutel met `Not authorized`. Zonder zo'n sleutel wordt er geen
  MQTT-verbinding geprobeerd en pollt de integratie gewoon door.

## Bronnen en datasets

Elke dataset is een **eigen instantie** van de integratie: je voegt ze los toe
(Integratie toevoegen → GRIB Weather Overlay) en kiest per instantie welke
parameters je wilt. Daarna staan ze samen in de keuzelijst van de overlay-card
en naast elkaar in de modelvergelijking. Van alle bronnen hieronder heeft er
maar één een sleutel nodig.

### Waar kies ik uit?

| Ik wil… | Dataset |
| --- | --- |
| weer en wind, zo fijn mogelijk boven Nederland | `harmonie_arome_cy43_p1` (2 km) of `icon_d2` (2,2 km) |
| weer en wind voor een overtocht verderop in Europa | `harmonie_arome_cy43_p3` (DINI) |
| weer en wind verder dan drie dagen vooruit | `gfs` (tot 16 dagen) |
| golven op de Noordzee, dicht bij huis | `rws_swan_dcsm`, of `rws_swan_kuststrook` langs de kust |
| golven én deining, met piekperiodes | `ewam` of `dmi_wam_nsb` |
| deining die nog dagen onderweg is | `gwam` (+174 u) of `gfs_wave` (+384 u) |
| stroming en waterstand op de eigen kust | `rws_dcsm_zuno` |
| stroming met kwartierdetail voor het getij | `bsh_current_northsea` |
| watertemperatuur | `dmi_dkss_nsbs` |
| de Noorse zuidkust | `metno_oslofjord`, `metno_skagerrak`, `metno_sorlandet` |

Twee bronnen naast elkaar zetten is trouwens geen verspilling: dát is wat de
modelvergelijking-card laat zien.

### KNMI Data Platform (`knmi`) — sleutel nodig

Het Nederlandse model, en het fijnste dat er over eigen water bestaat. Vraag een
gratis Open Data-sleutel aan op het
[KNMI Developer Portal](https://developer.dataplatform.knmi.nl/).

- **`harmonie_arome_cy43_p1`** — HARMONIE-AROME over Nederland, 2 km, uurlijks
  tot +60 uur, elke 6 uur een nieuwe run. Negen parameters: wind, windstoten,
  temperatuur, dauwpunt, luchtvochtigheid, neerslag, luchtdruk, zicht en
  bewolking. Windstoten komen hier als u/v, dus mét richting.
- **`harmonie_arome_cy43_p3`** — hetzelfde model op het Europese DINI-domein
  (39–72°N, 25°W–40°O), op een geroteerd rooster dat bij het decoderen naar een
  gewoon geografisch rooster wordt geprojecteerd — inclusief het meedraaien van
  de wind naar echt noord/oost. Groter gebied, dus meer download en meer
  rekentijd dan Nederland.

Eén run is een tar-archief van ~850 MB, ook als je maar één parameter aanzet:
er is geen API om losse lead times op te halen. Houd de voorspellingshorizon
daarom niet hoger dan je nodig hebt.

```yaml
type: custom:grib-overlay-card
dataset: harmonie_arome_cy43_p1
parameter: wind_gust_10m
wind_unit: kn
```

### DWD Open Data (`dwd`) — geen sleutel

- **`ewam`** — het Europese golfmodel, ~0,05° over de Noordzee, de Atlantische
  Oceaan en de Middellandse Zee (30–66°N, 10,5°W–42°O), uurlijks tot +78 uur,
  twee runs per dag. Elf parameters: golfhoogte, en van deining én windgolven
  apart de hoogte, richting, gemiddelde periode en piekperiode.
- **`gwam`** — dezelfde velden wereldwijd op 0,25°, elke 3 uur tot **+174 uur**.
  Voor de Atlantische aanloop en voor deining die nog dagen onderweg is. Het
  wereldrooster wordt bij het decoderen teruggebracht tot 30–72°N, 40°W–30°O.
- **`icon_d2`** — weermodel op 2,2 km over Midden-Europa (43–58°N, 4°W–20°O),
  uurlijks tot +48 uur, elke 3 uur een nieuwe run. Dezelfde negen parameters als
  KNMI plus **CAPE**. Windstoten zijn hier het maximum van het afgelopen uur,
  dus zonder eigen richting, en neerslag komt als totaal sinds de start van de
  run — de integratie rekent dat om naar millimeters per uur.

ICON-D2 is per parameter per uur een los bestand van ~1 MB: met alle tien
parameters en 24 uur horizon is een run ~250 MB. Zet aan wat je gebruikt.

```yaml
type: custom:grib-overlay-card
dataset: gwam
parameter: swell_height
render_mode: wavevectors
```

### NOAA (`noaa`) — geen sleutel

Het lange eind. Grof (0,25°, ~25 km) vergeleken met HARMONIE of ICON-D2, maar
het enige model hier dat verder dan een paar dagen kijkt. Vier runs per dag,
uurlijks tot +120 uur en daarna elke 3 uur tot +384. Het gebied ligt vast op
40–65°N, 25°W–15°O: Biskaje en Ierland tot IJsland, Noorwegen en de Oostzee.

- **`gfs`** — dezelfde tien parameters als ICON-D2. Let op de neerslag: GFS
  levert een **intensiteit** (mm/u) waar KNMI en ICON-D2 een hoeveelheid per uur
  (mm) geven.
- **`gfs_wave`** — WAVEWATCH III, aangedreven door GFS: golfhoogte, piekperiode
  en richting van de dominante golf, plus deining en windgolven, en de wind
  waarmee het golfmodel is gevoed.

```yaml
type: custom:grib-overlay-card
dataset: gfs
parameter: pressure_msl
show_isobars: true
```

### Rijkswaterstaat (`rws`) — geen sleutel

De modellen die Rijkswaterstaat zelf gebruikt, via NOOS-Matroos. Alles uurlijks
tot +48 uur; de integratie haalt één run per 6 uur op om de dienst te ontzien.

- **`rws_dcsm`** — waterstand en oppervlaktestroming van de Noorse kust tot
  Noord-Spanje (43–64°N, 12°W–13°O) op 0,05°.
- **`rws_dcsm_zuno`** — het ZUNO-nest van datzelfde model: het Kanaal, de
  Nederlandse, Belgische en Duitse kust, de Wadden en de Duitse Bocht
  (49,4–57°N, 3,4°W–9,6°O) op 0,025°. Twee keer zo fijn, en daarmee de keuze
  voor wie langs de kust vaart. Draai niet allebei — dat is hetzelfde model
  twee keer.
- **`rws_swan_dcsm`** — SWAN-golven voor de Noordzee en het Kanaal (48–64°N,
  12°W–9°O) op 0,05°: golfhoogte (Hm0), periode (Tm-1,0) en richting (Th0).
- **`rws_swan_kuststrook`** — dezelfde velden voor de Nederlandse kuststrook
  (51–54,4°N) op 0,02°.

De waterstand is zoals het model hem levert, niet omgerekend naar NAP of een
lokaal peil.

```yaml
type: custom:grib-overlay-card
dataset: rws_dcsm_zuno
parameter: current
render_mode: particles
```

### DMI Open Data (`dmi`) — geen sleutel

Het Deense instituut, en de enige bron hier met watertemperatuur. Elke 6 uur een
nieuwe run.

- **`dmi_wam_nsb`** — WAM-golven voor Noordzee, Kanaal en Oostzee (47–66°N,
  13°W–30°O, ~5 km), uurlijks tot **+132 uur**.
- **`dmi_wam_natlant`** — dezelfde velden voor de Noord-Atlantische Oceaan
  (30–78°N, 69°W–30°O, 0,25°), inclusief de Golf van Biskaje en de Noorse kust.
- **`dmi_dkss_nsbs`** — het stormvloedmodel DKSS: oppervlaktestroming,
  waterstand en **watertemperatuur** van Skagerrak tot het Kanaal (48,5–65,9°N,
  vanaf 4,1°W), uurlijks tot +120 uur.

De DKSS-waterstand is ten opzichte van het gemiddelde zeeniveau van dát model,
niet ten opzichte van NAP; vergelijk hem niet één-op-één met Nederlandse peilen.
De standaardhorizon van 24 uur gebruikt maar een fractie van de 5 dagen die
deze modellen leveren.

```yaml
type: custom:grib-overlay-card
dataset: dmi_dkss_nsbs
parameter: water_temperature
```

### BSH (`bsh`) — geen sleutel

- **`bsh_current_northsea`** — oppervlaktestroming voor de hele Noordzee
  inclusief de Nederlandse, Belgische en noord-Franse kust (48,6–60,6°N,
  3,9°W–8,9°O, ~5,5 km), tot +48 uur.

Het bijzondere hier is de tijdstap: **elk kwartier**, waar alle andere bronnen
uurlijks zijn. Dat geeft echte getijdetails, maar ook veel frames — 24 uur
horizon is 96 beelden.

```yaml
type: custom:grib-overlay-card
dataset: bsh_current_northsea
parameter: current
render_mode: vectors
```

### MET Norway (`metno`) — geen sleutel

Drie kant-en-klare gebieden langs de Noorse zuidkust, elk met weer, golven én
stroming in één dataset, op 0,05°: **`metno_oslofjord`** (58,9–60,0°N,
9,8–11,2°O), **`metno_skagerrak`** (57,7–59,4°N, 7,8–12,0°O) en
**`metno_sorlandet`** (57,8–58,8°N, 7,0–9,4°O).

Elk gebied combineert drie modellen: wind, neerslag en luchtdruk uit MEPS
(~66 uur), golven uit WAVEWATCH III op 4 km (~72 uur) en stroming op 3 meter
diepte uit NorKyst op 800 m (~120 uur). De stroming is dus niet aan het
oppervlak maar op diepte, en de bestanden zijn klein (0,2–1,2 MB).

```yaml
type: custom:grib-overlay-card
dataset: metno_skagerrak
parameter: current
```

## Vereisten

- Home Assistant OS of Supervised. Alle dependencies zijn pure-Python /
  universele wheels (`numpy`, `Pillow`, `paho-mqtt`); zowel GRIB1 (KNMI) als
  GRIB2 (DWD EWAM en ICON-D2, simple packing) worden door een meegeleverde eigen decoder
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
2. Kies de bron. Voor **KNMI Data Platform** vul je je Open Data API-sleutel in.
   Het veld **Notification Service API-sleutel** is optioneel en verwacht een
   *andere* sleutel, die je apart aanvraagt bij
   [developer.dataplatform.knmi.nl](https://developer.dataplatform.knmi.nl) →
   Notification Service. Laat het leeg als je die niet hebt — dan pollt de
   integratie, en dat is de enige zichtbare consequentie. Plak er **niet** je
   Open Data-sleutel in: die wordt geweigerd. Voor **DWD Open Data**, **BSH**,
   **DMI Open Data**, **Rijkswaterstaat** en **MET Norway** laat je de
   sleutel-velden leeg — die hebben geen sleutel nodig.
3. Kies een dataset. KNMI: HARMONIE-AROME Cy43 **Nederland** (standaard) of
   **Europa (DINI)**. DWD: **EWAM** (Europese golven) of **ICON-D2** (weermodel).
   DMI: **WAM Noordzee/Oostzee**, **WAM Noord-Atlantisch** (golven) of **DKSS**
   (stroming en waterstand). Rijkswaterstaat: **DCSM** (stroming en waterstand),
   **SWAN Noordzee** of **SWAN Nederlandse kust** (golven). MET Norway:
   **Oslofjord**, **Skagerrak** of **Sørlandet** (weer, golven en stroming).
   Wil je zowel weer als golven, voeg dan een integratie-instantie per dataset
   toe; in de kaart wissel je tussen instanties.
4. Kies welke parameters bijgehouden moeten worden. Dat kan later nog via
   **Configureren** (zie stap 5): zo zet je bijvoorbeeld deining aan op een
   bestaande EWAM-instantie, zonder die te verwijderen.
5. Optioneel: pas via de integratie-opties de **parameters**, de voorspellingshorizon (default
   24 uur; het maximum is wat de gekozen dataset zelf reikt — KNMI HARMONIE 60 uur,
   EWAM 78, de DMI-modellen 120–132, GWAM 174 en GFS 384), het aantal
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

De integratie levert **drie** Lovelace-cards:

- **`custom:grib-overlay-card`** — de kaart met GRIB-overlay, tijd-slider/animatie
  en het uitgebreide meteogram (alle parameters van elke bron op een punt).
- **`custom:grib-overlay-compare-card`** — een **modelvergelijking**: kies één
  parameter en zie op een punt (klik op de mini-kaart) wat de verschillende
  GRIB-bronnen voorspellen, als **lijngrafiek + tabel** per model. Dezelfde
  vergelijking zit ook in het uitgebreide meteogram onder **Weergave → “vergelijk
  modellen”**.
- **`custom:grib-overlay-weathermap-card`** — de **KNMI-weerkaart** met isobaren,
  hoge- en lagedrukgebieden en **fronten**: de laatste analyses en de
  verwachtingskaarten tot 48 uur vooruit.

### Overlay-card (`grib-overlay-card`)

Voeg een kaart van het type `custom:grib-overlay-card` toe, bijvoorbeeld via
de YAML-editor van een dashboard:

```yaml
type: custom:grib-overlay-card
# optioneel: vast een specifieke dataset/parameter kiezen bij het laden
# dataset: bsh_current_northsea   # datasetsleutel, -naam of de titel uit de keuzelijst
# entry_id: <config entry id>     # exacte config-entry (wint van dataset)
# parameter: wind_10m
# welke datasets/parameters deze kaart mag tonen (bv. golfdata op een eigen card):
# datasets: [knmi, dwd]         # alleen deze bronnen (source, datasetsleutel/-naam, titel of entry-id; * mag)
# exclude_datasets: [dmi_wam_*] # of juist deze bronnen niet
# parameters: [golven]          # alleen deze parameters (sleutel of groep; * mag)
# exclude_parameters: [golven]  # of juist deze parameters niet
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
# measurement_radius_km: 10   # meteogram → vergelijk modellen → Meting: straal voor nabije meetstations
```

#### Datasets verdelen over meerdere cards

Elke card kiest zelf welke datasets en parameters erin zitten. Zo houd je het
weer en de golven uit elkaar — twee cards naast elkaar op hetzelfde dashboard:

```yaml
# kaart 1: weer, zonder golfdata
type: custom:grib-overlay-card
exclude_parameters: [golven]

# kaart 2: alleen golven en deining
type: custom:grib-overlay-card
parameters: [golven]
```

- `datasets` / `exclude_datasets` kiezen de **bronnen**: match op `source`
  (`knmi`, `dwd`, `dmi`, `rws`, `metno`, `bsh`), datasetsleutel of -naam, de
  titel uit de keuzelijst of de entry-id. `*` mag als jokerteken
  (`dmi_*`, `rws_swan_*`).
- `parameters` / `exclude_parameters` kiezen de **parameters** binnen die
  bronnen: parametersleutels (`wave_height`), jokertekens (`swell_*`) of een
  groepsnaam: `golven` (alle golf-, deinings- en windgolf-parameters),
  `deining`, `windgolven`, `wind`, `zee` (stroming, waterstand,
  watertemperatuur) of `weer`.
- Een richting hoort bij zijn hoogte/periode: kies je `wave_height`, dan blijft
  `wave_direction` beschikbaar voor de pijlen (tenzij je die zelf uitsluit).
- Het filter geldt voor de hele card: de keuzelijst, de overlay én het
  uitgebreide meteogram. Een bron die niets overhoudt, verdwijnt uit de lijst;
  blijft er niets over, dan zegt de card dat.

### Modelvergelijking-card (`grib-overlay-compare-card`)

Vergelijk op één punt wat de verschillende bronnen voorspellen. Klik op de
mini-kaart om het punt te verzetten; kies boven de parameter en de kolom-tijdstap.

```yaml
type: custom:grib-overlay-compare-card
parameter: wind_10m          # startparameter (union van alle bronnen)
center: [52.98, 4.12]        # startpositie van de mini-kaart (bv. een haven)
zoom: 9
# meteogram_resolution: 3uur # kolom-tijdstap van de tabel: kwartier, uur, 3uur of dag
# datasets: [knmi, dwd]      # optioneel: alleen deze bronnen vergelijken
#                            #   (match op source, datasetsleutel/-naam, titel of entry-id; * mag)
#                            #   `entries:` / `models:` doen hetzelfde (oudere naam)
# exclude_datasets: [bsh]    # of juist deze bronnen niet
# parameters: [golven]       # alleen deze parameters in de keuzelijst (sleutel, * of groep)
# exclude_parameters: [zee]  # of juist deze parameters niet
# measurement_radius_km: 10  # straal voor "meetstations in de buurt" (standaard 10 km)
# eenheden gelden net als bij de overlay-card:
# wind_unit: kn
# direction_unit: deg
```

De vergelijking toont **alle bronnen die de gekozen parameter hebben** als
gekleurde lijnen + een tabel (rij per model). Modellen die het punt niet dekken
(bv. BSH landinwaarts) worden onderaan als “niet getoond” benoemd. Vink modellen
in/uit met de selectievakjes onder de kaart. De **modelnamen** worden **compact**
getoond (de bron-afkorting, bv. `KNMI` / `DWD` / `BSH`) — in de tabel, de
grafiek-legenda en de selectievakjes, én als bron-badge in het **uitgebreide
meteogram** — zodat op een smartphone de datakolommen en de meetwaarde-invoer de
ruimte houden; de **volledige naam** staat als tooltip. Heb je **meerdere modellen
van dezelfde bron** (bv. twee KNMI-datasets), dan krijgt elk een onderscheidende
toevoeging — een regio- (`KNMI NL` / `KNMI EU`) of modelnaam — zodat het verschil
duidelijk blijft. Wil je het zelf bepalen, geef dan per bron een **korte alias** op
in de integratie-opties (Configureren → *Korte alias*); die wordt dan overal als
compact label gebruikt.

**Meting & delta.** Vink **“Meting invoeren”** aan om per kolom een gemeten waarde
in te typen (in dezelfde eenheid als de grafiek). Je krijgt dan per model een
**Δ-rij** met **absolute** (model − meting) én **relatieve** (%) afwijking, plus een
samenvatting **bias (abs + %) / MAE / RMSE**; de meting verschijnt als donkere lijn
in de grafiek. Dezelfde meting/delta zit ook in het meteogram onder **Weergave →
“vergelijk modellen” → Meting**. Met **“Wis meting”** wis je de opgeslagen meting van
het punt in één klik; **“Wis alle meetdata”** wist de metingen van **alle** opgeslagen
punten tegelijk (na bevestiging; de knop toont hoeveel punten dat zijn en is grijs
als er niets is opgeslagen). Dat laatste lost het geval op waarin je op de telefoon
alle punten op één na kwijt kunt: een punt verdwijnt pas als je naar een ander punt
gaat, dus het laatste punt bleef staan.

**Meetstations downloaden.** Met “Meting invoeren” aan verschijnen de meetstations
binnen `measurement_radius_km` (standaard 10 km; ook via het straal-veld in de
werkbalk) als **groene stippen op de mini-kaart** en als **knoppen met afstand** —
**alleen stations die data hebben voor de gekozen parameter** (vooraf gecheckt bij
KNMI/RWS; water/golven/stroming van **RWS**, weer van **KNMI**). Klik een station — of
de knop **“Meetstation downloaden”** (dichtstbijzijnde) — om de **werkelijke
waarnemingen** op te halen en als meting te tonen/bewaren. Komt er toch niets terug,
dan wordt het station meteen verborgen. In de aparte vergelijk-card verspringt het punt
naar het station (voorspelling én meting op exact dezelfde plek); in het meteogram
blijft het punt staan (de meting komt dan van het nabije station, zoals een handmatige
waarde).

**Gecorreleerde voorspelling.** Kies bij **“Correctie”** *absoluut* (verschuiven) of
*relatief* (schalen) en vink de **bronnen** aan waarop je het toepast. Elke aangevinkte
bron krijgt een **gecorrigeerde rij + stippellijn**: zijn eigen gemiddelde afwijking
t.o.v. de meting over de overlappende (verleden) kolommen, vooruit doorgetrokken op de
hele voorspelling.

**Over de station-API's (verifiëren).** De koppelingen zijn best-effort geïmplementeerd:
KNMI via de **EDR**-API — `.../collections/10-minute-in-situ-meteorological-observations/locations/{id}`
(het dichtstbijzijnde station wordt uit `/locations` bepaald; `/position` bestaat hier
niet), met **dezelfde KNMI Open Data-sleutel** die de integratie al gebruikt en de
EDR-variabelen `ff`/`gff`/`dd`/`ta`/`td`/`rh`/`rg`/`pp`/`zm`. RWS via de **sleutelloze**
WaterWebservices **DDAPI20** (`ddapi20-waterwebservices.rijkswaterstaat.nl`:
`OphalenCatalogus` → dichtstbijzijnde station → `OphalenWaarnemingen`, AQUO-grootheden
`Hm0`/`Tm02`/`Th0`/`STROOMSHD`+`STROOMRTG`; `Hm0` komt in cm en wordt naar m omgerekend) —
de klassieke `_DBO`-adressen zijn uitgezet; live getest op 16-09-2026. De exacte
KNMI-codes/aanroepen kunnen afwijken; bij een mislukking zie je nu een melding in de card
**én** een `WARNING` in de HA-log met de exacte oorzaak. De response-parsers zijn met
fixtures getest. *(Neerslag komt van KNMI als intensiteit `rg` in mm/u — geen directe som
per interval; hou daar rekening mee.)*

> **KNMI 403 bij downloaden?** Je HARMONIE-sleutel is vaak **niet** geautoriseerd voor de
> observations-dataset (KNMI antwoordt dan `403`). Maak/vraag op het
> [KNMI Developer Portal](https://developer.dataplatform.knmi.nl/) een sleutel met toegang
> tot `10-minute-in-situ-meteorological-observations` aan en zet die in de integratie-optie
> **Observaties API-sleutel** (Configureren). `401` = sleutel niet herkend.

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
  (dikkere lijnen) en/of `particle_base_opacity` (raster verder dimmen). De
  animatie kost alleen iets als je hem ziet: Home Assistant houdt de cards van
  een dashboardpagina die je niet open hebt gewoon in de pagina, en vanaf 0.38.0
  zet de card zichzelf dan stil (en de tijdsanimatie ook) tot je terugkomt.
- `vectors` — pijltjes (richting + grootte), gekleurd naar windsnelheid met een
  contour; **alleen voor wind**.
- `wavevectors` — pijltjes voor de golfrichting; **alleen voor golven**. De
  pijlen horen bij de gekozen soort: golven, deining of windgolven.

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

### Weerkaart-card (`grib-overlay-weathermap-card`)

```yaml
type: custom:grib-overlay-weathermap-card
# title: Weerkaart   # optioneel; standaard "KNMI-weerkaart"
```

Toont de weerkaart van het KNMI zoals het KNMI hem tekent: isobaren, H/L en
warme, koude en occlusiefronten over Europa en de oostelijke Atlantische Oceaan.
Je bladert met ◀ ▶ (op een telefoon ook door te vegen) of kiest een kaart in de
lijst: de laatste vier **analyses** (om 00, 06, 12 en 18 UTC, ongeveer een uur
later beschikbaar) en de **verwachtingskaarten** daarna, tot 48 uur vooruit. De
card begint bij de nieuwste analyse en ververst de lijst elke 10 minuten. Tijden
staan in je eigen tijdzone, met het UTC-uur erbij dat op de kaart zelf staat.

- **Sleutel:** de kaarten komen uit de KNMI-dataset `weather_maps` en gebruiken de
  Open Data-sleutel van je KNMI-integratie; zonder KNMI-integratie meldt de card dat.
- **Opslag:** Home Assistant haalt de kaarten op en bewaart ze (~50 KB per stuk)
  in de cachemap.
- **Geen kaartlaag:** het zijn plaatjes in de eigen projectie van het KNMI, dus ze
  worden niet over de andere kaarten gelegd.

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

## Vier voorbeeld-cards

Vier startpunten, elk met precies de YAML die hem oplevert. Plak de YAML in een
handmatige card en je krijgt wat eronder beschreven staat.

### Wind als deeltjes, met isobaren en drukcentra

```yaml
type: custom:grib-overlay-card
title: Wind en druk
dataset: harmonie_arome_cy43_p1
parameter: wind_10m
render_mode: particles
show_isobars: true
wind_unit: kn
center: [52.4, 4.3]
zoom: 7
```

De overlay-card in zijn meest gebruikte vorm: windsnelheid als kleurenlaag, de
deeltjes die met de wind meestromen, en de isobaren-laag eroverheen met **H**-
en **L**-centra. Wind in knopen.

### Golven, met richtingspijlen

```yaml
type: custom:grib-overlay-card
title: Golven en deining
parameters: [golven]
parameter: wave_height
render_mode: wavevectors
center: [53.2, 3.6]
zoom: 6
```

Dezelfde card, maar gefilterd op golfdata (`parameters: [golven]`) en in
`wavevectors`-weergave: de pijlen wijzen de golfrichting aan die bij de gekozen
hoogte hoort.

### Modelvergelijking op een punt

```yaml
type: custom:grib-overlay-compare-card
title: Modelvergelijking
parameter: wind_10m
meteogram_resolution: 3uur
wind_unit: kn
center: [52.4, 4.5]
zoom: 8
```

Klik een punt op de mini-kaart en elke geconfigureerde bron komt als lijn in de
grafiek en als rij in de tabel — hier drie modellen voor wind op 10 m, in
kolommen van 3 uur.

### De KNMI-weerkaart

```yaml
type: custom:grib-overlay-weathermap-card
title: Weerkaart
```

Analyses en verwachtingskaarten tot 48 uur vooruit, met fronten, isobaren en
drukgebieden — de kaart die het KNMI zelf publiceert.

> De voorbeelden staan ook in `dev/shots.html`, dat ze één voor één op een
> vaste breedte rendert tegen de mock-server (`?card=overlay`, `waves`,
> `compare`, `weathermap`). Een test bewaakt dat die pagina en de YAML
> hierboven niet uit elkaar lopen.
## Alle instellingen — referentie

Volledige, exacte lijst van alle sleutels en waarden die je in de integratie
(config-flow/opties) en in de card-YAML kunt gebruiken. De sleutels zijn
hoofdlettergevoelig; gebruik ze exact zoals hieronder.

### Bronnen (`source`)

| `source` | Naam | API-sleutel |
| --- | --- | --- |
| `knmi` | KNMI Data Platform | ja (Open Data-sleutel) |
| `dwd` | DWD Open Data | nee |
| `bsh` | BSH (zeestroming Noordzee) | nee |
| `dmi` | DMI Open Data | nee |
| `rws` | Rijkswaterstaat (NOOS-Matroos) | nee |
| `metno` | MET Norway | nee |
| `noaa` | NOAA GFS (NOMADS) | nee |

### Datasets (`dataset`)

| Bron | `dataset` | Naam | Grid | Horizon (max) | Stap |
| --- | --- | --- | --- | --- | --- |
| `knmi` | `harmonie_arome_cy43_p1` | HARMONIE-AROME Cy43 — Nederland | regulier lat/lon | 60 u | 1 u |
| `knmi` | `harmonie_arome_cy43_p3` | HARMONIE-AROME Cy43 — Europa (DINI) | rotated lat/lon | 60 u | 1 u |
| `dwd` | `ewam` | DWD EWAM — Europese golven | regulier lat/lon | 78 u | 1 u |
| `dwd` | `gwam` | DWD GWAM — wereldwijde golven (uitgesneden 30–72°N, 40°W–30°O) | regulier lat/lon, 0,25° | 174 u | 3 u |
| `dwd` | `icon_d2` | DWD ICON-D2 — weermodel 2,2 km | regulier lat/lon | 48 u | 1 u |
| `bsh` | `bsh_current_northsea` | BSH — Zeestroming Noordzee | regulier lat/lon | 48 u | 15 min |
| `dmi` | `dmi_wam_nsb` | DMI WAM — golven Noordzee en Oostzee (47–66°N, 13°W–30°O, ~5 km) | regulier lat/lon | 132 u | 1 u |
| `dmi` | `dmi_wam_natlant` | DMI WAM — golven Noord-Atlantisch (30–78°N, 69°W–30°O, 0,25°) | regulier lat/lon | 132 u | 1 u |
| `dmi` | `dmi_dkss_nsbs` | DMI DKSS — stroming en waterstand (48,5–65,9°N, vanaf 4,1°W, ~5 km) | regulier lat/lon | 120 u | 1 u |
| `rws` | `rws_dcsm` | RWS DCSM — stroming en waterstand (43–64°N, 12°W–13°O, 0,05°) | regulier lat/lon | 48 u | 1 u |
| `rws` | `rws_dcsm_zuno` | RWS DCSM-ZUNO — stroming en waterstand Zuidelijke Noordzee (49,4–57°N, 3,4°W–9,6°O, 0,025°) | regulier lat/lon | 48 u | 1 u |
| `rws` | `rws_swan_dcsm` | RWS SWAN — golven Noordzee en Kanaal (48–64°N, 12°W–9°O, 0,05°) | regulier lat/lon | 48 u | 1 u |
| `rws` | `rws_swan_kuststrook` | RWS SWAN — golven Nederlandse kust (51–54,4°N, 0,02°) | regulier lat/lon | 48 u | 1 u |
| `metno` | `metno_oslofjord` | MET Norway — Oslofjord (58,9–60,0°N, 9,8–11,2°O) | regulier lat/lon, 0,05° | 66–120 u | 1 u |
| `metno` | `metno_skagerrak` | MET Norway — Skagerrak (57,7–59,4°N, 7,8–12,0°O) | regulier lat/lon, 0,05° | 66–120 u | 1 u |
| `metno` | `metno_sorlandet` | MET Norway — Sørlandet (57,8–58,8°N, 7,0–9,4°O) | regulier lat/lon, 0,05° | 66–120 u | 1 u |
| `noaa` | `gfs` | NOAA GFS — wereldmodel (uitgesneden 40–65°N, 25°W–15°O) | regulier lat/lon, 0,25° | 384 u | 1 u (≤120 u), daarna 3 u |
| `noaa` | `gfs_wave` | NOAA GFS-Wave — wereldwijde golven (zelfde uitsnede) | regulier lat/lon, 0,25° | 384 u | 1 u (≤120 u), daarna 3 u |

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

**DWD** (`ewam` en `gwam`, identiek):

| `parameter` | Naam | Eenheid | Type |
| --- | --- | --- | --- |
| `wave_height` | Golfhoogte (significant) | m | scalar |
| `wave_period` | Golfperiode (gemiddeld) | s | scalar |
| `wave_direction` | Golfrichting (gemiddeld) | ° | scalar |
| `swell_height` | Deining: hoogte | m | scalar |
| `swell_period` | Deining: periode (gemiddeld) | s | scalar |
| `swell_peak_period` | Deining: piekperiode | s | scalar |
| `swell_direction` | Deining: richting | ° | scalar |
| `wind_wave_height` | Windgolven: hoogte | m | scalar |
| `wind_wave_period` | Windgolven: periode (gemiddeld) | s | scalar |
| `wind_wave_peak_period` | Windgolven: piekperiode | s | scalar |
| `wind_wave_direction` | Windgolven: richting | ° | scalar |

**DWD** (`icon_d2`) — dezelfde sleutels als KNMI, zodat de modelvergelijking ze
naast elkaar zet:

| `parameter` | Naam | Eenheid | Type |
| --- | --- | --- | --- |
| `wind_10m` | Wind (10m) | m/s | vector |
| `wind_gust_10m` | Windstoten (10m) | m/s | scalar (alleen snelheid) |
| `temperature_2m` | Temperatuur (2m) | °C | scalar |
| `dewpoint_2m` | Dauwpunt (2m) | °C | scalar |
| `humidity_2m` | Relatieve luchtvochtigheid (2m) | % | scalar |
| `precipitation` | Neerslag (per uur) | mm | scalar |
| `pressure_msl` | Luchtdruk (zeeniveau) | hPa | scalar |
| `visibility` | Zicht | km | scalar |
| `cloud_cover` | Bewolking | % | scalar |
| `cape` | CAPE (onweersenergie) | J/kg | scalar |

ICON-D2 levert neerslag als totaal sinds de start van de run; de integratie
rekent dat om naar de hoeveelheid per uur, net als bij KNMI. Windstoten zijn bij
ICON het maximum van het afgelopen uur, zonder eigen richting. Op het starttijdstip
van een run (+0 u) bestaan die twee nog niet, dus die beelden ontbreken daar.

**DMI** (`dmi_wam_nsb` en `dmi_wam_natlant`) — dezelfde sleutels als EWAM:

| `parameter` | Naam | Eenheid | Type |
| --- | --- | --- | --- |
| `wave_height` | Golfhoogte (significant) | m | scalar |
| `wave_period` | Golfperiode (gemiddeld) | s | scalar |
| `wave_peak_period` | Golf: piekperiode | s | scalar |
| `wave_direction` | Golfrichting (gemiddeld) | ° | scalar |
| `swell_height`, `swell_period`, `swell_direction` | Deining: hoogte, periode, richting | m, s, ° | scalar |
| `wind_wave_height`, `wind_wave_period`, `wind_wave_direction` | Windgolven: hoogte, periode, richting | m, s, ° | scalar |

**DMI** (`dmi_dkss_nsbs`):

| `parameter` | Naam | Eenheid | Type |
| --- | --- | --- | --- |
| `current` | Zeestroming (oppervlak) | m/s | vector |
| `water_level` | Waterstand | m | scalar |
| `water_temperature` | Watertemperatuur | °C | scalar |

**RWS** (`rws_dcsm` en `rws_dcsm_zuno`, identiek):

| `parameter` | Naam | Eenheid | Type |
| --- | --- | --- | --- |
| `current` | Zeestroming (oppervlak) | m/s | vector |
| `water_level` | Waterstand | m | scalar |

**RWS** (`rws_swan_dcsm` en `rws_swan_kuststrook`):

| `parameter` | Naam | Eenheid | Type |
| --- | --- | --- | --- |
| `wave_height` | Golfhoogte (significant, Hm0) | m | scalar |
| `wave_period` | Golfperiode (gemiddeld, Tm-1,0) | s | scalar |
| `wave_direction` | Golfrichting (gemiddeld, Th0) | ° | scalar |

**MET Norway** (`metno_oslofjord`, `metno_skagerrak`, `metno_sorlandet`):

| `parameter` | Naam | Eenheid | Type | Model, vooruit |
| --- | --- | --- | --- | --- |
| `wind_10m` | Wind (10m) | m/s | vector | MEPS, ~66 u |
| `precipitation` | Neerslag (per uur) | mm | scalar | MEPS, ~66 u |
| `pressure_msl` | Luchtdruk (zeeniveau) | hPa | scalar | MEPS, ~66 u |
| `wave_height` | Golfhoogte (significant) | m | scalar | WAVEWATCH III 4 km, ~72 u |
| `wave_direction` | Golfrichting (gemiddeld) | ° | scalar | WAVEWATCH III 4 km, ~72 u |
| `current` | Zeestroming (3 m diep) | m/s | vector | NorKyst 800 m, ~120 u |

**NOAA** (`gfs`) — dezelfde sleutels als KNMI en ICON-D2:

| `parameter` | Naam | Eenheid | Type |
| --- | --- | --- | --- |
| `wind_10m` | Wind (10m) | m/s | vector |
| `wind_gust_10m` | Windstoten (10m) | m/s | scalar (alleen snelheid) |
| `temperature_2m` | Temperatuur (2m) | °C | scalar |
| `dewpoint_2m` | Dauwpunt (2m) | °C | scalar |
| `humidity_2m` | Relatieve luchtvochtigheid (2m) | % | scalar |
| `precipitation` | Neerslag (intensiteit) | mm/u | scalar |
| `pressure_msl` | Luchtdruk (zeeniveau) | hPa | scalar |
| `visibility` | Zicht | km | scalar |
| `cloud_cover` | Bewolking | % | scalar |
| `cape` | CAPE (onweersenergie) | J/kg | scalar |

Let op de neerslag: KNMI en ICON-D2 geven een **hoeveelheid per uur** (mm), GFS
een **intensiteit op dat moment** (mm/u). GFS begint zijn neerslagtotaal elke
zes uur opnieuw, dus totalen van elkaar aftrekken zou het uur op elke grens
kwijtmaken; de momentane intensiteit heeft dat probleem niet. In de
modelvergelijking staan ze dus naast elkaar maar zijn ze niet één op één
hetzelfde getal.

**NOAA** (`gfs_wave`) — dezelfde sleutels als EWAM en DMI:

| `parameter` | Naam | Eenheid | Type |
| --- | --- | --- | --- |
| `wave_height` | Golfhoogte (significant) | m | scalar |
| `wave_peak_period` | Golf: piekperiode | s | scalar |
| `wave_direction` | Golfrichting (primaire golf) | ° | scalar |
| `swell_height`, `swell_period`, `swell_direction` | Deining: hoogte, periode, richting | m, s, ° | scalar |
| `wind_wave_height`, `wind_wave_period`, `wind_wave_direction` | Windgolven: hoogte, periode, richting | m, s, ° | scalar |
| `wind_10m` | Wind (10m) | m/s | vector |

GFS-Wave geeft periode en richting van de **dominante** golf, waar EWAM en DMI
een gemiddelde over het hele spectrum geven; vandaar `wave_peak_period` in
plaats van `wave_period`. Deining komt bij GFS-Wave in partities (gesorteerd op
energie); de integratie toont de eerste, de dominante deiningstrein. De
wind-parameter is de wind waarmee het golfmodel is aangedreven, zodat zeegang en
wind erboven uit hetzelfde bestand komen.

**BSH** (`bsh_current_northsea`):

| `parameter` | Naam | Eenheid | Type |
| --- | --- | --- | --- |
| `current` | Zeestroming (oppervlak) | m/s | vector |

Het **type** bepaalt welke weergaven beschikbaar zijn: `vector`-parameters
(`wind_10m`, KNMI's `wind_gust_10m`, `current`) ondersteunen `particles`/`vectors`;
een richting-parameter (eenheid °, bv. `wave_direction`) schakelt `wavevectors`
in; en `pressure_msl` (eenheid hPa) schakelt de isobaren-laag in. Een richting
hoort bij de hoogte en periode met hetzelfde voorvoegsel: `swell_direction` bij
`swell_height`, `swell_period` en `swell_peak_period`. Zet je deining aan, neem
dan ook `swell_direction` mee, anders hebben de deining-rijen geen pijlen.

### Integratie: setup-velden (config-flow)

| Sleutel | Waarden |
| --- | --- |
| `source` | `knmi`, `dwd`, `bsh`, `dmi`, `rws`, `metno` of `noaa` |
| `api_key` | KNMI Open Data-sleutel (leeg laten voor DWD/BSH) |
| `notification_api_key` | optioneel; **aparte** KNMI Notification Service-sleutel (leeg, of je Open Data-sleutel = alleen pollen) |
| `dataset` | een dataset-sleutel uit de tabel hierboven |
| `parameters` | lijst van parameter-sleutels die je wilt bijhouden (later te wijzigen via de opties) |

### Integratie: opties (Configureren)

| Sleutel | Type | Default | Bereik / vorm |
| --- | --- | --- | --- |
| `parameters` | lijst | de keuze bij het toevoegen | welke parameters van de dataset gedownload en getoond worden. Een parameter die je aanzet verschijnt zodra de huidige run opnieuw is verwerkt; dat begint direct na opslaan |
| `forecast_horizon_hours` | getal (uren) | `24` | Van 1 tot wat de dataset zelf reikt (60 bij HARMONIE, 78 bij EWAM, 174 bij GWAM, 384 bij GFS). Maak je hem langer, dan wordt de huidige run direct opnieuw verwerkt; korter knipt de al verwerkte run in |
| `retain_runs` | geheel getal | `2` | 1–10 |
| `update_interval_minutes` | geheel getal (min) | `30` | 5–180 |
| `notification_api_key` | tekst | (leeg) | **aparte** KNMI Notification Service-sleutel voor push. Niet je Open Data-sleutel: die weigert de broker met `Not authorized`. Leeg = alleen pollen, geen MQTT-poging |
| `observations_api_key` | tekst | (leeg) | KNMI Open Data-sleutel mét toegang tot `10-minute-in-situ-meteorological-observations`, voor het **downloaden van stationswaarnemingen**. Je HARMONIE-sleutel heeft daar vaak géén toegang toe (KNMI geeft 403). Leeg = HARMONIE-sleutel hergebruiken |
| `alias` | tekst | (leeg) | **korte naam** voor deze bron, getoond als compact label in de vergelijking en het meteogram (bv. `KNMI NL`). Leeg = automatisch afgeleid uit de bron (bronnen van dezelfde soort worden vanzelf onderscheiden) |
| `storage_path` | tekst | (leeg) | **map voor de werkbestanden** (run-archief, uitgepakte bestanden, gerenderde cache). Leeg = `/var/tmp/grib_overlay`: in geen enkele back-up, en geleegd bij een HA-update (daarna wordt alles opnieuw gedownload). Zet dit **nooit** in een map die je back-up meeneemt (zie [Back-ups](#back-ups)) |
| `color_scales` | meerregelige tekst | (leeg) | per regel: `parameter: waarde:#hex, waarde:#hex, …` (waarden in de **eigen eenheid** van de parameter) |

### Card-instellingen (Lovelace-YAML)

| Sleutel | Type | Default | Waarden / betekenis |
| --- | --- | --- | --- |
| `dataset` | tekst | (eerste) | datasetsleutel, -naam of titel — welke dataset bij het laden |
| `entry_id` | tekst | (eerste) | exacte config-entry-id (wint van `dataset`) |
| `parameter` | tekst | (eerste) | parametersleutel — welke parameter bij het laden |
| `datasets` | lijst of tekst | — | alleen deze bronnen op deze card; match op `source`, datasetsleutel/-naam, titel of entry-id, `*` als jokerteken. Leeg = alle |
| `exclude_datasets` | lijst of tekst | — | deze bronnen juist **niet** (zelfde match) |
| `parameters` | lijst of tekst | — | alleen deze parameters: sleutel, jokerteken of groep (`golven`, `deining`, `windgolven`, `wind`, `zee`, `weer`). Leeg = alle |
| `exclude_parameters` | lijst of tekst | — | deze parameters juist **niet** (bv. `[golven]` voor een weerkaart zonder golfdata) |
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
| `base_map` | tekst | `osm` | startondergrond: `osm` (OpenStreetMap) of `emodnet` (EMODnet-dieptekaart), zie [Kaartlagen](#kaartlagen) |
| `map_layers` | lijst of tekst | `[seamarks]` | lagen die aan staan: `seamarks`, `sport`, `depth`, `soundings`, `gebco` |
| `tile_url` | tekst | (leeg) | eigen tegelserver in plaats van OpenStreetMap, als Leaflet-sjabloon (`https://…/{z}/{x}/{y}.png`) |
| `tile_attribution` | tekst (HTML) | OpenStreetMap | bronvermelding bij `tile_url` |
| `columns` | `full` of getal | `full` | breedte in een Secties-dashboard |
| `rows` | getal | — | hoogte in grid-rijen (masonry) / begingrootte |
| `grid_options` | object | — | HA-eigen `{rows, columns}` (wint van `rows`/`columns`) |
| `wind_unit` | tekst | `m/s` | `m/s`, `kn`, `km/h`, `mph` |
| `visibility_unit` | tekst | `km` | `km`, `NM` |
| `direction_unit` | tekst | `compass` | `compass`, `deg` |
| `meteogram_parameters` | lijst of tekst | — | parametersleutels die in het uitgebreide meteogram **standaard zichtbaar** zijn; de rest start verborgen (in te schakelen via de chips). Leeg = alle rijen tonen. Match op parametersleutel, dus geldt voor álle bronnen |
| `meteogram_resolution` | tekst | `uur` | tijdstap van de meteogram-kolommen: `kwartier`, `uur`, `3uur` of `dag`. Bij `dag` het daggemiddelde (neerslag: dagsom); fijner = waarde op dat tijdstip. In het venster zelf ook via “Kolommen” te wisselen |

In de keuzelijst van de kaart staan **geen losse richtingparameters**
(golfrichting, deiningsrichting): een richting hoort bij zijn hoogte of periode
en wordt daar als pijlen bovenop getekend. Wil je er tóch één als kleurlaag,
noem hem dan expliciet met `parameter: wave_direction`.

`datasets`/`parameters` (en hun `exclude_`-varianten) gelden voor de hele card:
keuzelijst, overlay en het uitgebreide meteogram. Een richtingparameter blijft
staan zolang zijn hoogte/periode blijft staan (`wave_height` houdt
`wave_direction`), zodat de pijlen werken. Zie
[Datasets verdelen over meerdere cards](#datasets-verdelen-over-meerdere-cards).

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
| `base_map`, `map_layers`, `tile_url`, `tile_attribution` | | | kaartlagen, als bij de overlay-card |
| `datasets` (of `entries`/`models`) | lijst of tekst | — | alleen deze bronnen vergelijken; match op `source`, datasetsleutel/-naam, titel of entry-id, `*` als jokerteken. Leeg = alle bronnen die de parameter hebben |
| `exclude_datasets` | lijst of tekst | — | deze bronnen juist **niet** |
| `parameters` / `exclude_parameters` | lijst of tekst | — | welke parameters in de keuzelijst staan: sleutel, jokerteken of groep (`golven`, `zee`, `weer` …) |
| `meteogram_resolution` | tekst | `uur` | kolom-tijdstap van de tabel: `kwartier`, `uur`, `3uur`, `dag` |
| (geen sleutel) | | | de parameterlijst volgt de **aangevinkte** modellen: vink je een bron uit, dan verdwijnen de parameters die alleen die bron heeft |
| `wind_unit`, `visibility_unit`, `direction_unit` | tekst | zie hieronder | zelfde eenheden-opties als de overlay-card |

### Weerkaart-card (`grib-overlay-weathermap-card`)

| Sleutel | Type | Default | Waarden / betekenis |
| --- | --- | --- | --- |
| `title` | tekst | `KNMI-weerkaart` | kop van de card |

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

### Kaartlagen

Rechtsboven op beide kaarten zit een **lagenknop**, met dezelfde zeekaartlagen
als [map.openseamap.org](https://map.openseamap.org):

| Laag | `id` | Wat | Bron |
| --- | --- | --- | --- |
| OpenStreetMap | `osm` | ondergrond (standaard) | OpenStreetMap |
| EMODnet-dieptekaart | `emodnet` | ondergrond: reliëf van land en zeebodem, Europese zeeën | EMODnet Bathymetry |
| Zeetekens | `seamarks` | boeien, bakens, lichten, vaargeulen (standaard aan) | OpenSeaMap |
| Sport | `sport` | jachthavens, surf-, duik- en zeilplekken | OpenSeaMap |
| Dieptelijnen | `depth` | dieptecontouren uit dieptemetingen van gebruikers (beta, niet overal) | OpenSeaMap |
| Dieptemetingen | `soundings` | de gemeten diepte langs gevaren routes, als gekleurde stippen | OpenSeaMap |
| GEBCO-diepte | `gebco` | wereldwijde diepte-inkleuring van de zee, half doorzichtig | GEBCO 2021 via OpenSeaMap |

Met `base_map` en `map_layers` kies je waarmee een card start. Wat je daarna in
de lagenknop aanklikt, onthoudt de browser voor beide cards; dat gaat dan voor
op de card-instellingen.

```yaml
type: custom:grib-overlay-card
base_map: emodnet
map_layers: [seamarks, soundings, gebco]
```

Dit zijn hulplagen, geen officiële zeekaart: gebruik ze niet voor navigatie.

#### OpenStreetMap en "Access blocked"

OpenStreetMap draait op vrijwilligersservers en blokkeert sinds september 2026
apps die zich niet aan het [tegelbeleid](https://operations.osmfoundation.org/policies/tiles/)
houden: je ziet dan tegels met **"Access blocked"**. Daarom:

- **Home Assistant 2026.9 en nieuwer:** de tegels komen via Home Assistant zelf
  (`/api/map_tiles`, net als bij de eigen kaarten van Home Assistant). Home
  Assistant haalt ze op onder zijn eigen naam en bewaart ze een week; de card
  vraagt daarvoor een kortlevend token op en vernieuwt dat vanzelf.
- **Oudere Home Assistant:** de card gaat rechtstreeks naar
  `https://tile.openstreetmap.org` en stuurt daarbij de verplichte `Referer` mee
  (alleen het adres van je Home Assistant, niet het dashboardpad).
- **Eigen tegelserver:** zet `tile_url` (en `tile_attribution`) in de card;
  die vervangt OpenStreetMap in de lagenknop.

## Prestaties

Wat de integratie doet om licht te blijven, en wat je daarvan merkt. De cijfers
hieronder zijn gemeten op een echte instance met **veertien** ingestelde
bronnen.

- **De zware roosters gaan gecomprimeerd over de lijn.** Eén windframe is
  ruim 200 kB aan getallen-als-tekst — het grootste dat de card ooit ophaalt —
  en dat is ongeveer **vier keer** zo klein gezipt. De gezipte kopie wordt de
  eerste keer dat een frame wordt opgevraagd naast het bestand gelegd en gaat
  weg met de run waar hij bij hoort, dus er is geen rekenwerk per verzoek.
- **Ook de lijsten gaan gecomprimeerd.** De frame-lijst van één bron is 49 kB
  aan tijdstempels en urls; die wordt in het geheugen gemaakt, dus daar ligt
  geen gezipte kopie naast — hij wordt op de uitgang gezipt. Korte antwoorden
  blijven ongemoeid: onder een paar kB kost de kop meer dan hij bespaart.
- **Het volgende frame wordt pas vooruit geladen als je het nodig hebt.** Tijdens
  het afspelen, en zodra je zelf door de tijd geschoven hebt. Op een pagina waar
  alleen naar gekeken wordt, scheelt dat een tweede kaartafbeelding van ruim
  100 kB die niemand ooit ziet.
- **Een kaartpagina haalt niets dubbel op.** De caches in de card bewaren het
  *verzoek*, niet het antwoord; twee delen van de card die tegelijk om
  hetzelfde frame vragen, wachten nu op dezelfde ophaalactie. En alle cards op
  een pagina delen één lijst met bronnen in plaats van er elk één op te halen.
- **De weerkaart laat zien wat hij heeft.** KNMI's kaarten opvragen en
  binnenhalen duurt een paar seconden en de kaarten veranderen maar om de paar
  uur, dus je krijgt meteen de lijst die er al is en wordt de nieuwe erachter
  opgehaald. Alleen een card die nog helemaal niets heeft, wacht.
- **Elke bron heeft zijn eigen moment.** Home Assistant start ze allemaal in
  dezelfde seconde, dus zonder meer zouden veertien bronnen elk half uur
  tegelijk gaan downloaden en decoderen. Elke bron wacht nu eerst zijn eigen
  plek in het interval af, afgeleid van zijn id, dus die plek is na elke
  herstart dezelfde.
- **Cards die je niet ziet, doen niets.** De deeltjesanimatie en de
  tijdsanimatie slapen zolang de card niet in beeld is, en de weerkaart slaat
  zijn tien-minutenpoll over voor een pagina die niemand open heeft.

## Sleutels & problemen oplossen

KNMI gebruikt **drie losse sleutels**. Ze zijn niet uitwisselbaar; een sleutel
op de verkeerde plek wordt geweigerd.

| Optie | Waarvoor | Zonder |
| --- | --- | --- |
| **API-sleutel** (Open Data) | het ophalen van de forecast-runs zelf | de integratie werkt niet |
| **Notification Service API-sleutel** | push via MQTT, direct bij een nieuwe run | alleen pollen — verder niets |
| **Observaties API-sleutel** | stationswaarnemingen downloaden in de vergelijking | geen meetstations |

Wat je in het logboek ziet (Instellingen → Systeem → Logboek):

- **`the API key was rejected`** — de **Open Data-sleutel** deugt niet en deze
  bron werkt niet meer. De melding vertelt welk van de twee gevallen het is:
  `401` = de sleutel wordt niet herkend (typefout, half geplakt, verlopen of
  ingetrokken); `403` = de sleutel wordt wél herkend maar heeft **geen toegang
  tot deze dataset**. Eén keer gelogd, niet bij elke poll; zodra hij weer werkt
  verschijnt `the API key is accepted again`.
- **`KNMI Notification Service rejected the connection`** — de
  **Notification Service-sleutel** deugt niet. Pollen loopt gewoon door, dus dit
  is niet urgent. Staat er niets in het notificatieveld (of je Open Data-sleutel,
  wat op hetzelfde neerkomt), dan wordt er geen verbinding geprobeerd en zie je
  ook geen melding.
- **`Connected to the KNMI Notification Service`** — push werkt. Dit is een
  `INFO`-regel, dus die verschijnt zonder debug-logging aan te zetten; zo kun je
  controleren dát je notificatiesleutel goed staat in plaats van te moeten raden.
- **`KNMI EDR /locations HTTP 401/403`** — de **observaties-sleutel**. Alleen de
  meetstations werken dan niet; de rest van de kaart draait door.
- **`KNMI weather charts unavailable`** — de KNMI-weerkaart kon niet worden
  opgehaald; de melding zegt waarom (bijv. een geweigerde sleutel). De rest van de
  integratie werkt gewoon door.
- **Kaarttegels met "Access blocked"** — de ondergrond; zie
  [Kaartlagen](#kaartlagen). Werk bij naar 0.29.1 of nieuwer en
  ververs het dashboard (de browser bewaart de geblokkeerde tegels even).
- **Een kaart op een andere dashboardpagina toont de hele wereld met een
  spikkeltje overlay (of lijkt leeg)** — die card werd opgebouwd terwijl zijn
  pagina nog verborgen was, dus paste Home Assistant de dataset in een kaart
  zonder afmetingen: Leaflet komt dan uit op zoomniveau 0. Sinds 0.37.7 wacht de
  card met inzoomen tot hij echt een grootte heeft, en doet hij het alsnog zodra
  je die pagina opent.
- **Kaart en overlay blijven leeg na het wisselen van dashboard, de rest van de
  card werkt wel** — Leaflet komt soms terug zonder dat er iets getekend is.
  Sinds 0.37.5 meet de card zichzelf een paar keer opnieuw op en bouwt hij de
  kaart desnoods opnieuw op, op dezelfde plek en met hetzelfde tijdstip; de
  overlay-afbeelding wordt opnieuw aangemaakt als zijn beeld niet meer op de
  kaart zit.
- **De kaart blijft leeg als je tussen dashboardpagina's bladert** — Home
  Assistant houdt de kaarten van een pagina in het geheugen en hangt ze er bij
  terugkomst weer in. Sinds 0.37.3 haalt de card bij zo'n terugkeer zijn frames
  opnieuw op, meet hij de kaart opnieuw op en toont hij hetzelfde tijdstip als
  daarvoor — verversen van de pagina is niet meer nodig.
- **Een parameter blijft leeg terwijl de rest van de bron werkt** — in het
  logboek staat dan `Run … : no data for <parameter>`. Die run wordt daarna nog
  één keer opnieuw verwerkt (bij een herstart of herladen van de integratie);
  blijft hij leeg, dan is het die run zelf en vult de eerstvolgende run hem
  gewoon weer.
- **Isobaren staan aan maar er verschijnt niets** — onder de kaart staat dan
  *"Geen luchtdrukdata voor dit tijdstip"*. De run is nog niet verwerkt (even
  wachten), of je hebt luchtdruk pas net aangezet: de integratie haalt die run
  dan opnieuw op bij de volgende poll. In de browserconsole staat er een regel
  bij met de parameter en het tijdstip.
- **Het vinkje "Isobaren" is grijs** — deze bron heeft geen luchtdruk in deze
  card. Zet `pressure_msl` aan bij Instellingen → Apparaten & diensten → GRIB
  Weather Overlay → Configureren, en controleer dat je hem niet wegfiltert met
  `parameters`/`exclude_parameters`. De isobaren worden altijd uit de luchtdruk
  van de **getoonde dataset zelf** getekend, dus een andere bron met luchtdruk
  helpt niet. De tooltip van het vinkje zegt dit ook.
- **Welke versie draait de browser, en hoe kwam die binnen?** De card meldt
  zich in de browserconsole:
  `GRIB-OVERLAY-CARD 0.37.8 loaded in 5 ms (from cache)`. Die regel draait als
  laatste van het bestand: staat hij er niet, dan is het bestand niet (volledig)
  geladen en komt een "Configuratiefout" daarvandaan. Staat hij er wel, dan zegt
  de tijd erachter of het bestand van de schijf kwam of over de lijn moest.
- **Het kaartvak is nul pixels hoog** (0.40.1) — Leaflet zet `position:
  relative` rechtstreeks op de map-div zodra het de positie ervan als `static`
  afleest, en dat is wat een element meldt zolang het nog niet in de pagina
  hangt: precies de toestand van een card die Home Assistant aan het opbouwen is
  bij een dashboardwissel. Die inline stijl wint het van onze eigen `position:
  absolute; inset: 0`, waardoor `inset` niets meer doet en de map tot niets
  inklapt — de card staat er, de knoppen werken, het kaartvak is leeg, en dat
  blijft zo tot je de pagina ververst. De card geeft het element nu terug aan
  zijn eigen stylesheet, zodra Leaflet klaar is én telkens als hij weer in beeld
  komt.
- **De kaart staat er, maar de map en de overlay zijn leeg** — meestal na een
  wissel naar een ander dashboard: Leaflet gooit de tegels van een map weg die
  uit de pagina gehaald wordt, en opnieuw opmeten alleen haalt ze niet terug.
  Elke card (ook de modelvergelijking) kijkt zelf of zijn map leeg is zodra hij
  weer in beeld komt, en tekent hem opnieuw — met een verse poging bij élke
  terugkeer, niet twee keer per browsersessie. Vanaf 0.39.0 telt daarbij alleen
  wat de browser écht getekend heeft: Leaflet houdt elke tegel onzichtbaar tot
  de afbeelding binnen is, dus een map met afgebroken tegelverzoeken (wat een
  browser doet met een stuk pagina dat verdwijnt — Chromium het snelst) stond
  vól tegels én volledig leeg, en gold daarvóór ten onrechte als gezond. Blijft
  hij toch leeg, dan meldt de card dat zelf in het logboek en als melding, met
  de afmeting van de container erbij.
- **Rode blokken op de plek van álle GRIB-cards, alleen na een refresh, alleen
  in Chromium-browsers (Vivaldi, Edge, Chrome)** — dit is opgelost in 0.40.0.
  Home Assistant zet dit bestand als `<script type="module">` in de pagina, dus
  de browser voert het uit náást HA's eigen bundel. Bij een refresh komt het uit
  de cache van de service worker en is het eerder klaar — en die bundel
  vervángt daarna `window.customElements` door een eigen, lege registratie, die
  niets weet van elementen die daarvóór geregistreerd zijn. De cards zijn dan
  perfect in orde (`document.createElement("grib-overlay-card")` geeft gewoon de
  juiste klasse), maar `customElements.get(...)` — precies de vraag die Home
  Assistant stelt vóór het bouwen van een card — antwoordt "bestaat niet", en je
  krijgt een rood blok. Vanaf 0.40.0 vertelt de card die nieuwe registratie over
  zijn eigen drie namen (verder wordt er niets aangeraakt) en vraagt hij Home
  Assistant de card opnieuw te bouwen. Meestal gebeurt dat binnen de twee
  seconden die HA wacht, zodat je het rode blok niet eens ziet.
- **"Configuratiefout" zonder tekst eronder** — Home Assistant vervangt een
  card door zo'n leeg blok als het toekennen van `hass`, `preview` of `layout`
  aan de card een fout geeft. Vlak daarvoor zet het een regel in de
  browserconsole met het kaarttype en de fout erbij. **Vanaf 0.38.0 hoef je daar
  niet meer zelf bij te zijn:** de card leest die regel zelf mee en stuurt hem
  naar de integratie. Je krijgt dan een melding in Home Assistant
  ("de card gaf een fout in de browser") met de foutmelding erin, en dezelfde
  tekst staat in het logboek (Instellingen → Systeem → Logboek). Daarbij staat
  ook of de pagina geladen of **ververst** werd, welke browser het was, en of er
  meer dan één kopie van het cardbestand geladen is. Vanaf 0.39.0 gaat de card
  bovendien **zelf zoeken** naar zo'n rood blok op de pagina — dat werkt ook als
  een andere card de console heeft overgenomen — en zegt erbij welke andere
  cards er rood staan. Dezelfde fout wordt vijf
  minuten lang maar één keer gemeld, zodat het logboek niet volloopt.
- **"Configuratiefout" op de plek van de card** — Home Assistant wacht maar een
  paar seconden tot een custom card zich meldt; haalt de browser de card niet op
  tijd binnen (traag netwerk, mobiel, veel custom cards naast elkaar), dan komt
  die melding in beeld en helpt verversen. Vanaf 0.36.1 wordt alles in de
  `www`-map **gecomprimeerd** en **een maand gecached** aangeboden — de URL
  bevat de versie, dus na een update haalt de browser vanzelf het nieuwe bestand
  op. Staat er een andere tekst onder "Configuratiefout" (bijvoorbeeld over een
  onbekende sleutel), dan gaat het om de YAML van de card zelf.

Meer detail nodig? Zet in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.grib_overlay: debug
```

## Taal

De cards en de integratie spreken **de taal die de Home Assistant-gebruiker zelf
heeft gekozen** (Profiel → Taal). Geleverd worden **Nederlands** en **Engels**;
elke andere taal valt terug op Engels. Er is niets in te stellen — de card leest
de taal uit `hass.locale.language`.

Wat er meegaat:

| | Voorbeeld NL | Voorbeeld EN |
| --- | --- | --- |
| Knoppen, labels, tooltips | “Wis meting”, “Meetstations binnen 10 km:” | “Clear measurement”, “Stations within 10 km:” |
| Meldingen en foutteksten | “Geen model heeft data voor deze parameter op dit punt.” | “No model has data for this parameter at this point.” |
| Parameternamen | Windstoten (10m), Luchtdruk (zeeniveau) | Wind gusts (10 m), Pressure (mean sea level) |
| Datasetnamen | HARMONIE-AROME Cy43 - **Nederland** … | HARMONIE-AROME Cy43 - **Netherlands** … |
| Windrichting (kompas) | `N/NO/O/ZO/Z/ZW/W/NW` | `N/NE/E/SE/S/SW/W/NW` |
| Datums en tijden in grafiek en tabel | `za 05-09, 06:00` | `Sat 05/09, 06:00` |
| Woord-eenheden | `km/u`, `zeemijl` | `km/h`, `nmi` |

Twee kanttekeningen:

- **De config- en optiesflow** volgt de taal van de *instantie* (Instellingen →
  Systeem → Algemeen), niet die van de individuele gebruiker: een config flow
  heeft de gebruikerstaal niet tot zijn beschikking. In de praktijk is dat
  dezelfde taal. De veldnamen zelf komen uit Home Assistants eigen
  vertaalbestanden (`translations/nl.json`, `translations/en.json`); de
  dataset- en parameterlijsten worden pas tijdens het draaien bij de bron
  opgehaald en worden daarom door de integratie zelf vertaald.
- **Namen van meetstations en plaatsen** (Schiphol, Hoek van Holland, K13-A)
  blijven zoals ze zijn — dat zijn eigennamen.

Een taal toevoegen betekent: een blok bijzetten in `GRIB_TEXT`,
`GRIB_PARAM_NAMES`, `GRIB_DATASET_NAMES` en `GRIB_COMPASS` in
`grib-overlay-card.js`, plus `labels.py` en een `translations/<taal>.json`.

## Back-ups

**De integratie schrijft niets meer in een map die een back-up kan meenemen.**
Alle werkbestanden — run-archieven, uitgepakte GRIB-bestanden en de gerenderde
PNG/JSON-cache — zijn opnieuw te downloaden en horen niet in een back-up:

| Wat | Standaardlocatie |
| --- | --- |
| **Cache** (gerenderde beelden per run) | `/var/tmp/grib_overlay/<integratie>/…` |
| **Werkbestanden tijdens een download** | `/var/tmp/grib_overlay/.raw/<integratie>/…` |
| **KNMI-weerkaarten** | `/var/tmp/grib_overlay/weather_maps/` |

Waarom dat ertoe doet:

- **Grootte.** Met een handvol bronnen is de cache al snel 1–2 GB, en kaartbeelden
  laten zich nauwelijks comprimeren.
- **Betrouwbaarheid.** Verdwijnt een bestand precies tussen "back-up
  inventariseert" en "back-up schrijft", dan faalt de **hele** back-up met
  `FileNotFoundError`. Deze integratie ruimt voortdurend bestanden op.

`/config` gaat altijd mee in een back-up, en `/share` en `/media` als je die in
de back-upinstellingen aanvinkt; Supervisor kan geen losse map uitsluiten. De
enige knop is dus de locatie. `/var/tmp` is binnen de Home Assistant-container
gewoon schijf en zit in geen enkele back-upmap.

**Gevolg:** bij een update van Home Assistant wordt de container opnieuw
aangemaakt en is `/var/tmp` leeg. De integratie downloadt dan bij de volgende
poll gewoon alles opnieuw; tot die tijd zijn de kaarten leeg. Een gewone herstart
laat de cache staan.

Waarom niet `/tmp`? Dat is binnen HAOS een *tmpfs* (RAM), en een archief van
~850 MB hoort niet in je geheugen.

Met de optie **Map voor werkbestanden** kies je desgewenst zelf een pad (cache en
werkbestanden komen dan daar). Zet dat nooit binnen `/config`, en ook niet in
`/share` of `/media` als je back-up die meeneemt.

Extra's:

- **Automatische opruiming bij het updaten.** Oudere versies bewaarden de cache in
  `/config/grib_overlay` (tot v0.25) en `/share/grib_overlay` (v0.26–v0.34). Bij de
  eerste start na de update worden die mappen verwijderd — niet terwijl er een
  back-up loopt — en is je volgende back-up direct kleiner. Zie het `WARNING` in
  het logboek. Een map die je zelf als **Map voor werkbestanden** hebt ingesteld,
  blijft staan.
- **Ruwe downloads apart.** Het archief en de uitgepakte bestanden staan naast de
  run-mappen, zodat het opruimen van oude runs nooit een lopende download raakt.
- **Pauze tijdens de back-up.** Via HA's back-up-platform pauzeert de integratie
  het verwerken en opruimen van runs zolang een back-up loopt: een vangnet voor het
  opruimen hierboven en voor wie de map bewust in een back-upmap zet.

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
- Van **DWD Open Data** worden de golfmodellen **EWAM** en **GWAM** en het
  weermodel **ICON-D2** ondersteund. Die gebruiken eenvoudige GRIB2-packing en
  zijn dus zonder binaire library te lezen. ICON-EU en ECMWF niet: die gebruiken
  CCSDS/AEC-compressie, waarvoor zo'n library wél nodig is. Het kustgolfmodel
  CWAM is wel leesbaar maar begint pas op 6,2°O — oostelijk van Ameland — en
  wordt daarom (nog) niet aangeboden.
- **GWAM** staat op het hele wereldrooster (1440 × 699 punten). De integratie
  snijdt bij het decoderen een vast gebied uit — **30–72°N, 40°W–30°O**, van de
  breedte van de Canarische Eilanden tot ruim boven Noorwegen en van
  mid-Atlantisch tot de Oostzee. Dat is geen bezuiniging: de wind- en
  veld-endpoints dunnen een rooster uit tot een vast aantal punten per as, dus
  een wereldveld zou boven de Noordzee veel grover aankomen dan het model is.
  Het gebied staat vast en is niet in te stellen.
- **NOAA GFS en GFS-Wave** lopen via NCEP's NOMADS-*filter*-dienst, niet via de
  ruwe bestanden. Dat moet ook: de bestanden op NCEP's eigen servers gebruiken
  complexe packing met spatial differencing (template 5.3), die de decoder hier
  niet leest — de filterdienst herverpakt jouw selectie als eenvoudige packing.
  Diezelfde dienst snijdt server-side een gebied uit, dus een tijdstap met álle
  parameters is enkele honderden kilobytes in plaats van honderden megabytes.
  Het gebied staat vast op **40–65°N, 25°W–15°O**. Per tijdstap gaat er één
  verzoek naar NOMADS (alle ingeschakelde parameters tegelijk), met hoogstens
  twee tegelijk: het is een gratis publieke dienst.
- **GFS-runs** verschijnen tijdstap voor tijdstap, vanaf ongeveer 3 uur 20 na
  de runtijd; +384 uur staat er pas uren later. Voordat er iets gedownload
  wordt, kijkt de integratie met één verzoek van één gridcel of de láátste
  tijdstap die jouw horizon nodig heeft al online staat. Zo niet, dan wacht ze
  tot de volgende poll en houd je ondertussen de vorige run. Hoe langer je
  horizon, hoe later een nieuwe run dus binnenkomt — dat is geen fout en staat
  alleen in het debug-log.
- **DCSM-ZUNO** is hetzelfde Rijkswaterstaat-model als `rws_dcsm`, maar het
  nest voor de Zuidelijke Noordzee: kleiner gebied, twee keer zo fijn gevraagd
  (0,025° in plaats van 0,05°). Ongeveer 0,8 MB per uur, dus ~20 MB voor een run
  van 24 uur. Draai je beide, dan vraag je hetzelfde model twee keer op —
  meestal wil je alleen het nest.
- **ICON-D2** is per parameter per uur een los bestand van ~1 MB. Met alle 10
  parameters en de standaardhorizon van 24 uur is een run dus ~250 MB download
  (48 uur: ~500 MB). Er komt elke 3 uur een nieuwe run, zo'n 80 minuten na de
  runtijd. De integratie pakt een run (ook bij EWAM, dat ~35 minuten over het
  publiceren doet) pas op als die compleet op de server staat.
  Zet alleen de parameters aan die je gebruikt, of verhoog het poll-interval.
- **BSH-zeestroming** is 15-minuten-data: één BSH-bestand bevat een heel etmaal
  aan tijdstappen (96 per 24 u). De integratie splitst dat in losse tijdstappen,
  maar houd er rekening mee dat een langere voorspellingshorizon veel frames
  oplevert (24 u = 96 frames). Alleen het BSH-Noordzee-gebied wordt ondersteund
  (dat dekt de NL/BE/FR-kust); de fijnere deelgebieden en de Oostzee nog niet.
- **DMI** publiceert per run één bestand per uur. Bij WAM is dat 1–2 MB per uur;
  van DKSS (9 MB per uur, vooral stroming op tientallen diepten) leest de
  integratie alleen het begin met de oppervlaktevelden, ~0,3 MB per uur. Er komt
  elke 6 uur een nieuwe run, ~2,5 uur na de runtijd; een run wordt pas opgepakt
  als alle uren online staan. Zet de voorspellingshorizon op wat je nodig hebt
  (bijv. 120) — de standaard 24 uur gebruikt maar een deel van de 5 dagen.
- **Waterstand** is bij DMI DKSS de hoogte ten opzichte van het gemiddelde
  zeeniveau van dat model, niet ten opzichte van NAP; vergelijk hem niet
  één-op-één met Nederlandse peilen.
- **Rijkswaterstaat** (NOOS-Matroos) rekent elke aanvraag op eigen servers om
  naar een regelmatig rooster. Om die dienst te ontzien haalt de integratie één
  run per 6 uur op (de modellen draaien elke 3 uur), in stukken van 7 uur. Voor
  DCSM is dat ~2,5 MB per uur voor het hele gebied (24 uur vooruit: ~60 MB per
  run); SWAN Noordzee ~1,6 MB en SWAN-kust ~0,7 MB per uur. De modellen reiken
  tot 48 uur vooruit. Matroos zet een run al in de lijst zodra de eerste uren
  klaar zijn, dus de integratie vraagt eerst met één klein verzoek of het laatste
  uur er al is; zo niet, dan blijft de vorige (complete) run staan tot de nieuwe
  af is — meestal een half uur later.
- **DCSM-waterstand**: de omrekening naar een regelmatig rooster levert langs
  kusten en in afgesloten bekkens een handvol onmogelijke waarden (8–12 m). De
  integratie verwijdert cellen die meer dan 2 m van hun buren afwijken (~0,04%);
  echte uitschieters zoals springtij bij Saint-Malo blijven staan. De waterstand
  is zoals het model hem levert, niet omgerekend naar een lokaal peil.
- **MET Norway** levert per gebied kant-en-klare bestanden (0,2–1,2 MB). Weer,
  golven en stroming worden elk op hun eigen moment ververst (weer ongeveer elk
  uur); bij elke update haalt de integratie de bestanden voor de gekozen
  parameters opnieuw op. Elke inhoud heeft zijn eigen runtijd en reikwijdte (zie
  de tabel). De stroming is die op 3 m diepte. De dienst eist dat een app zich
  identificeert; de integratie stuurt daarvoor haar naam en projectadres mee.
  Gegevens: MET Norway, CC BY 4.0.

## Ontwikkelen & testen

```bash
python3 -m pip install -r requirements-dev.txt  # numpy, Pillow, paho-mqtt, homeassistant, pytest-homeassistant-custom-component
python3 -m pytest tests/
```

Een paar losse dev-hulpmiddelen werken zonder Home Assistant:

- `dev/verify_knmi_source.py` — controleert de KNMI-source-implementatie
  tegen de echte Open Data API (dataset-catalogus, file listing, download-URL).
- `dev/render_preview.py <grib-bestand>` — decodeert en rendert alle
  geconfigureerde parameters uit één GRIB-lead-time-bestand naar PNG's in
  `dev/output/`, handig om colormaps/reprojectie visueel te controleren.
- `dev/mock_server.py` + `dev/dev.html` — draait de kaart-kaart in een echte
  browser tegen een nagebootste API (hergebruikt de PNG's uit
  `dev/render_preview.py`), zonder dat er een Home Assistant-instantie nodig is.
  Met `?lang=en` (of `?lang=nl`) bootst de harness de taalkeuze van de
  HA-gebruiker na, zodat je beide talen kunt controleren.
- `dev/shots.html` — rendert de vier voorbeeld-cards uit
  [Vier voorbeeld-cards](#vier-voorbeeld-cards) los van elkaar op een vaste
  breedte, elk op zijn eigen URL (`/shots.html?card=overlay`, `waves`,
  `compare`, `weathermap`), tegen diezelfde mock-server. De YAML staat in die
  pagina zelf en een test bewaakt dat de README dezelfde blokken toont.
- `python3 dev/toc.py` — bouwt de twee inhoudsopgaven opnieuw uit de koppen van
  de README. Draai dit als je een hoofdstuk toevoegt of hernoemt;
  `tests/test_readme.py` faalt anders.
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

---

<a id="english"></a>

# GRIB Weather Overlay for Home Assistant — English

> **Taal / Language:** 🇬🇧 English · 🇳🇱 [Nederlandse documentatie](#grib-weather-overlay-voor-home-assistant) (top of this page)

Shows GRIB weather data (wind, precipitation, temperature, pressure, visibility,
cloud cover, ...) as a colour layer over an [OpenSeaMap](https://map.openseamap.org)
map in Home Assistant. Pick a single time with a slider, or a start/end/step to
play an animation of the forecast.

Data sources (via a `GribSource` interface, so sources can be added without
changing the map card or the rest of the backend):

- [KNMI Data Platform](https://dataplatform.knmi.nl/) — HARMONIE-AROME
  (Netherlands and Europe/DINI), GRIB1. Requires a free Open Data key.
- [DWD Open Data](https://opendata.dwd.de/) — the **EWAM** (European seas) and
  **GWAM** (global, to +174 hours) wave models, with wave height, swell and wind
  waves including direction and period, plus the **ICON-D2 weather model**
  (2.2 km, all of the Netherlands and the southern North Sea), GRIB2, **no key**.
- [BSH](https://www.bsh.de/) — **sea current** (surface u/v) for the whole North
  Sea including the Dutch, Belgian and northern French coast, 15-minute steps,
  GRIB1, **no key** (open FTP).
- [DMI](https://www.dmi.dk/friedata) — the Danish **WAM** wave model
  (North Sea/Baltic at ~5 km and the North Atlantic at 0.25°) and the **DKSS**
  storm-surge model (currents, water level and water temperature from the
  Skagerrak to the Channel), up to 5 days ahead, GRIB1, **no key**.
- [Rijkswaterstaat](https://noos.matroos.rws.nl/) (NOOS-Matroos) — the **DCSM**
  model (water level and currents from the Norwegian coast to northern Spain, plus
  the finer **ZUNO nest** for the southern North Sea) and the **SWAN** wave models
  (North Sea, and at a fine grid along the Dutch coast), 48 hours ahead, NetCDF,
  **no key**.
- [MET Norway](https://api.met.no/weatherapi/gribfiles/1.1/documentation) —
  weather (MEPS), waves (4 km) and currents (800 m model) for the **Oslofjord,
  Skagerrak and Sørlandet**, 3 to 5 days ahead, GRIB1, **no key**.
- [NOAA](https://nomads.ncep.noaa.gov/) (NCEP NOMADS) — the **GFS** global model
  and the **GFS-Wave** wave model, both to **+384 hours** at 0.25°: the only model
  here that looks further than a few days, GRIB2, **no key**.

## Contents

- [Features](#features-1)
- [Sources and datasets](#sources-and-datasets)
  - [Which one do I pick?](#which-one-do-i-pick)
  - [KNMI Data Platform (`knmi`) — key required](#knmi-data-platform-knmi--key-required)
  - [DWD Open Data (`dwd`) — no key](#dwd-open-data-dwd--no-key)
  - [NOAA (`noaa`) — no key](#noaa-noaa--no-key)
  - [Rijkswaterstaat (`rws`) — no key](#rijkswaterstaat-rws--no-key)
  - [DMI Open Data (`dmi`) — no key](#dmi-open-data-dmi--no-key)
  - [BSH (`bsh`) — no key](#bsh-bsh--no-key)
  - [MET Norway (`metno`) — no key](#met-norway-metno--no-key)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Adding cards to a dashboard](#adding-cards-to-a-dashboard)
- [Four example cards](#four-example-cards)
- [All settings — reference](#all-settings--reference)
  - [Sources (`source`)](#sources-source)
  - [Datasets (`dataset`)](#datasets-dataset-1)
  - [Parameters (`parameter` / `parameters`)](#parameters-parameter--parameters-1)
  - [Integration: setup fields (config flow)](#integration-setup-fields-config-flow)
  - [Integration: options (Configure)](#integration-options-configure)
  - [Card settings (Lovelace YAML)](#card-settings-lovelace-yaml)
  - [Model-comparison card (`grib-overlay-compare-card`)](#model-comparison-card-grib-overlay-compare-card-1)
  - [Weather-map card (`grib-overlay-weathermap-card`)](#weather-map-card-grib-overlay-weathermap-card-1)
  - [Units (valid values + aliases)](#units-valid-values--aliases)
  - [Map layers](#map-layers)
- [Performance](#performance)
- [Keys & troubleshooting](#keys--troubleshooting)
- [Language](#language)
- [Backups](#backups)
- [Known limitations](#known-limitations)
- [Development & testing](#development--testing)
- [Architecture / adding new sources](#architecture--adding-new-sources)
- [License](#license)

## Features

- Configurable parameters: wind (10m), gusts, temperature (2m), dew point (2m),
  relative humidity (2m), precipitation, mean-sea-level pressure, visibility,
  cloud cover.
- **Waves** (DWD EWAM): significant wave height, mean wave direction and wave
  period as a colour layer over the European seas — with a meteogram and a
  value-under-the-cursor, just like the other parameters.
- **Swell and wind waves** (DWD EWAM) separately: height, direction, mean period
  and peak period of each. The direction arrows follow the selected kind: when
  you look at swell, the arrows show the swell direction.
- **A second high-resolution weather model** (DWD ICON-D2, 2.2 km): the same
  parameters as KNMI HARMONIE plus **CAPE** (energy for thunderstorms), a new run
  every 3 hours out to +48 hours. The parameters share their keys, so the model
  comparison lines both models up directly.
- **Sea current** (BSH): surface current (speed + direction) for the North Sea
  as a colour layer with particles/arrows — like wind, but for the water. At
  15-minute resolution, so fine tidal detail.
- **Waves, currents and water level up to 5 days ahead** (DMI): WAM waves from
  the Oslofjord to northern Spain, and currents, water level and water
  temperature from the Skagerrak to the Channel.
- **Rijkswaterstaat water level and currents** (DCSM) from the Norwegian coast to
  northern Spain, and waves for the North Sea and, finely, the Dutch coast (SWAN)
  — the models Rijkswaterstaat uses itself.
- **The Norwegian end** (MET Norway): wind, precipitation, pressure, waves and
  currents, right into the Oslofjord.
- **Looking far ahead** (NOAA GFS and GFS-Wave, to +384 hours): where HARMONIE,
  ICON-D2 and EWAM stop after two or three days, GFS runs on to sixteen. It is
  coarse (0.25°), so not a replacement for the fine-mesh models but the
  complement to them — and thanks to a server-side cut-out a lead time costs
  only tens of kilobytes.
- **Waves for the Atlantic approaches** (DWD GWAM, to +174 hours): the same
  fields as EWAM, but global and more than twice as far ahead — for swell that
  is still days away.
- **KNMI weather map with fronts** as its own card: analyses and forecast charts
  up to 48 hours ahead.
- **Pick per card which datasets it holds** (`datasets` / `parameters` and their
  `exclude_` variants): give the waves a card of their own and keep the weather
  card clean — the filter applies to the detailed meteogram too.
- **Nautical chart layers** as on map.openseamap.org: seamarks, sport, depth
  contours, depth soundings, GEBCO depth and an EMODnet bathymetry base map, via a
  layer button on the map.
- A single-time slider and an animation mode (start, end, step, playback speed).
- **Windy.com-style animated wind particles** (via the bundled `leaflet-velocity`),
  alongside the coloured raster overlay. Choose "Wind (particles)" on the map for
  a wind parameter; the particles flow with the wind direction over a dimmed
  speed map. There is also a **"Wind (vectors)"** mode with arrows (direction +
  magnitude); the arrows are **coloured by wind speed** (the same colours as the
  raster legend) with a white outline so they stay legible over the overlay.
- **Isobars + pressure centres** as a separate layer: tick **"Isobars"** and you
  get pressure contour lines every 4 hPa (the round 20 hPa lines thicker) with
  value labels on top, plus **H**igh (blue) and **L**ow (red) pressure centres
  with their core pressure. This lays **over any other overlay of the same
  dataset** (e.g. wind + isobars), as long as that dataset has a pressure
  parameter. The pressure is taken from that same integration's pressure
  parameter. *(Fronts/occlusions are drawn by analysts and are not in the open
  GRIB data; they are deliberately not included yet.)*
- **Value under the cursor** (for every parameter) is shown live at the bottom
  left of the map, in the configured units; for wind also the direction.
  **Click/tap** pins the value in a popup, and **press-and-hold / right-click**
  opens a dismissable **meteogram** (value-over-time at that point) with major
  gridlines and minor ticks on both axes. For **wind**, **wind and gusts are
  drawn together** on the same speed axis — with a gust envelope (a band between
  wind and gust) — and on the **second y-axis** both the **wind and gust
  direction** (compass N/E/S/W). Gusts must be enabled as a parameter for this.
- **Value inspector on every chart.** Move the **mouse over** a chart (or
  **tap/drag with your finger**) and a vertical guideline appears with a tooltip
  showing the **time (x)** and the **value(s) (y)** at that point — in the
  meteogram, in the model comparison and in the compare mode. With multiple
  lines, each model appears with its own value in the tooltip.
- **Detailed meteogram (all parameters & sources).** At the bottom of every value
  and meteogram popup is the link **“Alle parameters & bronnen ▸”** (All
  parameters & sources). It opens a Windy-style **table meteogram**: one row per
  parameter, colour-coded value cells, and all rows on the **same time axis**
  (columns). It shows **all available GRIB data at that point from every
  configured integration** (KNMI, DWD, BSH …), grouped by source; sources with a
  different time step simply fill their own columns (the rest stays empty). Cell
  colours and units follow exactly the **colour scales** configured on the
  card/integration (including custom `color_scales`) and the **units**
  (`wind_unit`, `visibility_unit`, `direction_unit`); directions are shown as an
  **arrow and a number** (compass or 0–360°). **Tap a row label** to temporarily
  hide that row (so you can view a limited set side by side); hidden rows come
  back via the chips at the top or **“Alle rijen tonen”** (Show all rows). The
  default selection is set with the card option
  [`meteogram_parameters`](#card-settings-lovelace-yaml). With the **“Kolommen”**
  (Columns) selector at the top (or the card option `meteogram_resolution`) you
  choose the column time step: **quarter-hour, hour, 3-hour or day**. For
  quarter/hour/3-hour the **actual value at that time** is shown (not an
  average); for **day** the **daily average** of all data that day (a
  vector/compass average for direction). **Precipitation** is the exception: it
  is **summed** per column — the total over the period *ending* at that column
  (e.g. the 3-hour column `03` = precipitation of 01+02+03; the `00` column =
  22+23 of the previous day plus 00), and the daily sum for the day step. While
  it is being built the popup shows a **loading indicator**; the data is fetched
  per source in **one request** (the `point_all` endpoint), so opening stays fast.
- **Model comparison.** A second card (`custom:grib-overlay-compare-card`) and a
  mode in the meteogram (**Weergave → “vergelijk modellen”**, i.e. View → compare
  models) show what the **different GRIB sources** predict at one point for **one
  parameter**: a **line chart** with a line per model (Windy-style) plus a
  **table** with a row per model (the same quarter/hour/3-hour/day columns,
  colours and units). In the separate card you pick the point on a **mini-map**
  (OpenStreetMap + OpenSeaMap) and tick models on/off. The **chosen point is
  shared** with the regular overlay card and vice versa (click on one, the other
  adopts it).
- **Measurement & delta.** In the comparison, enable **“Meting invoeren”** (Enter
  measurement) to type a **measured value** per column. The measurement appears
  as a dark line in the chart and as a row in the table, and each model gets a
  **Δ row** with the **absolute** (**measurement − model**; `+` = measurement higher
  than the source) and the **relative** (%) deviation, plus a summary: **bias (abs +
  %), MAE and RMSE**. That tells you at a
  glance which model is closest to reality. Entered measurements are **saved per
  point + parameter** (in `localStorage`, so they persist across reloads and are
  available in every card view): the point gets an **amber pin** on **every** map
  (overlay and compare card), and clicking it reopens the point with its saved
  values — also in the overlay card's meteogram (View → compare models).
  **“Wis meting”** (Clear measurement) removes the saved measurement in one click,
  and **“Wis alle meetdata”** (Clear all measurement data) discards the
  measurements of **every** saved point at once — with a confirmation, and with
  the number of points on the button. That last one matters on a phone, where a
  point is only dropped by moving to another one, so the last point could never
  be cleared.
- **Download measurement stations.** Once “Meting invoeren” is on, the **measurement
  stations within an adjustable radius** (default **10 km**, via
  `measurement_radius_km` or the radius field) appear as **green dots on the
  mini-map** and as **buttons with distance**. Only stations that **actually have data
  for the chosen parameter** are offered (the integration asks KNMI/RWS up front), and
  **water/waves/current** stations come from **RWS** while weather comes from **KNMI**.
  Click a station — or the **“Meetstation downloaden”** button (nearest) — to **fetch
  its real observations** and show/store them as the measurement, exactly like a
  hand-entered value. If a station still returns nothing, it is hidden immediately. In
  the separate compare card the point moves to the station (forecast and measurement at
  the exact same place); in the meteogram the point stays put (the measurement then
  comes from the nearby station, like a manual value). *(The live KNMI/RWS API calls
  are best-effort and should be verified on your own HAOS with your KNMI key.)*
- **Corrected ("gecorreleerde") forecast.** Under **“Correctie”** choose *absolute*
  (shift) or *relative* (scale) and tick **which sources** to apply it to. Each ticked
  source gets a **corrected row + dashed line**: its own average deviation from the
  measurement over the overlapping (past) columns, carried forward across the whole
  forecast.
- **Shared click position.** The clicked position is shared between the overlay
  card and the compare card (also across dashboard pages, for the session). In
  the overlay card the **value window** opens at that position immediately (and
  closes the previous one).
- Map with an OpenStreetMap base layer + OpenSeaMap seamark layer + the GRIB
  overlay, fully independent of an internet connection for the map JS itself
  (Leaflet is bundled, no CDN dependency for the code — the OSM/OpenSeaMap map
  tiles of course still come from the internet).
- Only the configured parameters and the configured time range are
  decoded/rendered; older forecast runs are cleaned up automatically
  (configurable).
- New forecast runs are fetched immediately via KNMI's MQTT Notification Service
  (instead of waiting for the next poll), with the regular polling interval as a
  reliable fallback if the MQTT connection fails for any reason. This needs a
  **separate Notification Service key**: that service authorises independently of
  Open Data and refuses an Open Data key with `Not authorized`. Without such a
  key no MQTT connection is attempted and the integration simply keeps polling.

## Sources and datasets

Every dataset is its **own instance** of the integration: you add them
separately (Add integration → GRIB Weather Overlay) and pick the parameters you
want per instance. They then sit together in the overlay card's picker and side
by side in the model comparison. Of all the sources below, only one needs a
key.

### Which one do I pick?

| I want… | Dataset |
| --- | --- |
| weather and wind, as fine as it gets over the Netherlands | `harmonie_arome_cy43_p1` (2 km) or `icon_d2` (2.2 km) |
| weather and wind for a crossing elsewhere in Europe | `harmonie_arome_cy43_p3` (DINI) |
| weather and wind further than three days ahead | `gfs` (up to 16 days) |
| waves on the North Sea, close to home | `rws_swan_dcsm`, or `rws_swan_kuststrook` along the coast |
| waves *and* swell, with peak periods | `ewam` or `dmi_wam_nsb` |
| swell that is still days away | `gwam` (+174 h) or `gfs_wave` (+384 h) |
| currents and water level on your own coast | `rws_dcsm_zuno` |
| currents in quarter-hour detail for the tide | `bsh_current_northsea` |
| water temperature | `dmi_dkss_nsbs` |
| the south coast of Norway | `metno_oslofjord`, `metno_skagerrak`, `metno_sorlandet` |

Running two sources side by side is not a waste, by the way: that is exactly
what the model-comparison card shows.

### KNMI Data Platform (`knmi`) — key required

The Dutch model, and the finest there is over Dutch water. Request a free Open
Data key at the
[KNMI Developer Portal](https://developer.dataplatform.knmi.nl/).

- **`harmonie_arome_cy43_p1`** — HARMONIE-AROME over the Netherlands, 2 km,
  hourly to +60 h, a new run every 6 hours. Nine parameters: wind, gusts,
  temperature, dew point, humidity, precipitation, pressure, visibility and
  cloud cover. Gusts arrive as u/v here, so with a direction of their own.
- **`harmonie_arome_cy43_p3`** — the same model on the European DINI domain
  (39–72°N, 25°W–40°E), on a rotated grid that is projected onto a plain
  geographic one while decoding — including turning the wind back to true
  north/east. A bigger area, so more download and more work than the Dutch one.

One run is a ~850 MB tar archive even if you enable a single parameter: there is
no API for individual lead times. Keep the forecast horizon no higher than you
need.

```yaml
type: custom:grib-overlay-card
dataset: harmonie_arome_cy43_p1
parameter: wind_gust_10m
wind_unit: kn
```

### DWD Open Data (`dwd`) — no key

- **`ewam`** — the European wave model, ~0.05° over the North Sea, the Atlantic
  and the Mediterranean (30–66°N, 10.5°W–42°E), hourly to +78 h, two runs a day.
  Eleven parameters: wave height, and for swell *and* wind waves separately the
  height, direction, mean period and peak period.
- **`gwam`** — the same fields globally at 0.25°, every 3 hours to **+174 h**.
  For the Atlantic approaches and for swell that is still days away. The global
  grid is cut down to 30–72°N, 40°W–30°E while decoding.
- **`icon_d2`** — a 2.2 km weather model over central Europe (43–58°N, 4°W–20°E),
  hourly to +48 h, a new run every 3 hours. The same nine parameters as KNMI plus
  **CAPE**. Gusts here are the maximum over the past hour, so without a direction
  of their own, and precipitation arrives as a total since the run started — the
  integration turns that into millimetres per hour.

ICON-D2 is a separate ~1 MB file per parameter per hour: with all ten parameters
and a 24-hour horizon a run is ~250 MB. Enable what you use.

```yaml
type: custom:grib-overlay-card
dataset: gwam
parameter: swell_height
render_mode: wavevectors
```

### NOAA (`noaa`) — no key

The long end. Coarse (0.25°, ~25 km) next to HARMONIE or ICON-D2, but the only
model here that looks further than a few days. Four runs a day, hourly to +120 h
and every 3 hours to +384 after that. The window is fixed at 40–65°N, 25°W–15°E:
Biscay and Ireland to Iceland, Norway and the Baltic.

- **`gfs`** — the same ten parameters as ICON-D2. Mind the precipitation: GFS
  gives a **rate** (mm/h) where KNMI and ICON-D2 give an amount per hour (mm).
- **`gfs_wave`** — WAVEWATCH III driven by GFS: wave height, peak period and
  direction of the dominant wave, plus swell and wind waves, and the wind the
  wave model was fed with.

```yaml
type: custom:grib-overlay-card
dataset: gfs
parameter: pressure_msl
show_isobars: true
```

### Rijkswaterstaat (`rws`) — no key

The models Rijkswaterstaat uses itself, through NOOS-Matroos. All hourly to
+48 h; the integration fetches one run per 6 hours to go easy on the service.

- **`rws_dcsm`** — water level and surface currents from the Norwegian coast to
  northern Spain (43–64°N, 12°W–13°E) at 0.05°.
- **`rws_dcsm_zuno`** — the ZUNO nest of that same model: the Channel, the
  Dutch, Belgian and German coast, the Wadden and the German Bight (49.4–57°N,
  3.4°W–9.6°E) at 0.025°. Twice as fine, and therefore the one to pick if you
  sail along the coast. Do not run both — that is the same model twice.
- **`rws_swan_dcsm`** — SWAN waves for the North Sea and the Channel (48–64°N,
  12°W–9°E) at 0.05°: wave height (Hm0), period (Tm-1,0) and direction (Th0).
- **`rws_swan_kuststrook`** — the same fields for the Dutch coastal strip
  (51–54.4°N) at 0.02°.

The water level is as the model delivers it, not converted to NAP or any local
datum.

```yaml
type: custom:grib-overlay-card
dataset: rws_dcsm_zuno
parameter: current
render_mode: particles
```

### DMI Open Data (`dmi`) — no key

The Danish institute, and the only source here with water temperature. A new run
every 6 hours.

- **`dmi_wam_nsb`** — WAM waves for the North Sea, the Channel and the Baltic
  (47–66°N, 13°W–30°E, ~5 km), hourly to **+132 h**.
- **`dmi_wam_natlant`** — the same fields for the North Atlantic (30–78°N,
  69°W–30°E, 0.25°), including the Bay of Biscay and the Norwegian coast.
- **`dmi_dkss_nsbs`** — the DKSS storm-surge model: surface currents, water
  level and **water temperature** from the Skagerrak to the Channel
  (48.5–65.9°N, from 4.1°W), hourly to +120 h.

DKSS's water level is relative to that model's own mean sea level, not to NAP;
do not compare it one to one with Dutch datums. The default 24-hour horizon uses
only a fraction of the 5 days these models deliver.

```yaml
type: custom:grib-overlay-card
dataset: dmi_dkss_nsbs
parameter: water_temperature
```

### BSH (`bsh`) — no key

- **`bsh_current_northsea`** — surface currents for the whole North Sea
  including the Dutch, Belgian and northern French coast (48.6–60.6°N,
  3.9°W–8.9°E, ~5.5 km), to +48 h.

What is special here is the time step: **every quarter of an hour**, where every
other source is hourly. That gives real tidal detail, but also a lot of frames —
a 24-hour horizon is 96 images.

```yaml
type: custom:grib-overlay-card
dataset: bsh_current_northsea
parameter: current
render_mode: vectors
```

### MET Norway (`metno`) — no key

Three ready-made areas along the south coast of Norway, each with weather, waves
*and* currents in one dataset, at 0.05°: **`metno_oslofjord`** (58.9–60.0°N,
9.8–11.2°E), **`metno_skagerrak`** (57.7–59.4°N, 7.8–12.0°E) and
**`metno_sorlandet`** (57.8–58.8°N, 7.0–9.4°E).

Each area combines three models: wind, precipitation and pressure from MEPS
(~66 h), waves from WAVEWATCH III at 4 km (~72 h) and currents at 3 metres depth
from NorKyst at 800 m (~120 h). So the current is not at the surface but at
depth, and the files are small (0.2–1.2 MB).

```yaml
type: custom:grib-overlay-card
dataset: metno_skagerrak
parameter: current
```

## Requirements

- Home Assistant OS or Supervised. All dependencies are pure-Python / universal
  wheels (`numpy`, `Pillow`, `paho-mqtt`); both GRIB1 (KNMI) and GRIB2 (DWD EWAM
  and ICON-D2, simple packing) are read by a bundled custom decoder, so **no** `eccodes`/`cfgrib`
  binary library is needed (that one does not have a wheel for every Python
  version/CPU and previously broke installation).
- A free API key from the
  [KNMI Developer Portal](https://developer.dataplatform.knmi.nl/) for the Open
  Data API.

## Installation

### Via HACS (recommended)

1. HACS → Integrations → menu (⋮) → Custom repositories.
2. Add the URL of this repository, category "Integration".
3. Search for "GRIB Weather Overlay" in HACS and install it.
4. Restart Home Assistant.

### Manual

1. Copy `custom_components/grib_overlay` to `/config/custom_components/`.
2. Restart Home Assistant.

## Configuration

1. Settings → Devices & services → Add integration → "GRIB Weather Overlay".
2. Choose the source. For **KNMI Data Platform** enter your Open Data API key.
   The **Notification Service API key** field is optional and expects a
   *different* key, requested separately at
   [developer.dataplatform.knmi.nl](https://developer.dataplatform.knmi.nl) →
   Notification Service. Leave it empty if you don't have one — the integration
   then polls, which is the only visible consequence. Do **not** paste your Open
   Data key there: it is refused. For **DWD Open Data**, **BSH**, **DMI Open
   Data**, **Rijkswaterstaat** and **MET Norway** leave the key fields empty —
   they need no key.
3. Choose a dataset. KNMI: HARMONIE-AROME Cy43 **Netherlands** (default) or
   **Europe (DINI)**. DWD: **EWAM** (European waves) or **ICON-D2** (weather
   model). DMI: **WAM North Sea/Baltic**, **WAM North Atlantic** (waves) or
   **DKSS** (currents and water level). Rijkswaterstaat: **DCSM** (currents and
   water level), **SWAN North Sea** or **SWAN Dutch coast** (waves). MET Norway:
   **Oslofjord**, **Skagerrak** or **Sørlandet** (weather, waves and currents). If you want both weather and waves, add one integration instance per
   dataset; in the card you switch between instances.
4. Choose which parameters should be kept up to date. You can change that later
   under **Configure** (see step 5) — for instance to switch swell on for an
   existing EWAM instance without removing it.
5. Optional: via the integration options, adjust the **parameters**, the forecast horizon (default
   24 hours; the maximum is however far the chosen dataset itself reaches — KNMI
   HARMONIE 60 hours, EWAM 78, the DMI models 120–132, GWAM 174 and GFS 384),
   the number of forecast runs to keep (default 2), the polling interval (default
   30 minutes) and **custom colour scales per parameter** (see below).

### Custom colour scales

In the integration options you can define, per parameter, between which colours
the overlay interpolates — so you can, for example, make visible which wind speed
you still find acceptable and which not. This is **baked into the map render (PNG)**
at full resolution, so the legend and the arrows follow the scale automatically.

The **"Custom colour scales"** field takes one parameter per line:

```
wind_10m: 0:#2c7fb8, 8:#7fcdbb, 12:#ffffb2, 16:#fd8d3c, 24:#bd0026
temperature_2m: -10:#313695, 0:#ffffbf, 35:#a50026
```

- The **values are in the parameter's own unit** (m/s, °C, hPa, mm, m).
- Below the lowest and above the highest stop the colour is held.
- A parameter without a line keeps the built-in colours.
- A change **re-renders the current run** (in the background) so the new colours
  come through immediately — this is meant as a setting you rarely change.

## Adding cards to a dashboard

The integration provides **three** Lovelace cards:

- **`custom:grib-overlay-card`** — the map with the GRIB overlay, time
  slider/animation and the detailed meteogram (all parameters of every source at
  a point).
- **`custom:grib-overlay-compare-card`** — a **model comparison**: pick one
  parameter and see, at a point (click on the mini-map), what the different GRIB
  sources predict, as a **line chart + table** per model. The same comparison is
  also in the detailed meteogram under **Weergave → “vergelijk modellen”** (View →
  compare models).
- **`custom:grib-overlay-weathermap-card`** — the **KNMI weather map** with
  isobars, high and low pressure centres and **fronts**: the latest analyses and
  the forecast charts up to 48 hours ahead.

### Overlay card (`grib-overlay-card`)

Add a card of type `custom:grib-overlay-card`, for example via a dashboard's YAML
editor:

```yaml
type: custom:grib-overlay-card
# optional: fix a specific dataset/parameter on load
# dataset: bsh_current_northsea   # dataset key, name, or the title from the picker
# entry_id: <config entry id>     # exact config entry (wins over dataset)
# parameter: wind_10m
# which datasets/parameters this card may show (e.g. wave data on a card of its own):
# datasets: [knmi, dwd]         # only these sources (source, dataset key/name, title or entry-id; * allowed)
# exclude_datasets: [dmi_wam_*] # or rather not these sources
# parameters: [waves]           # only these parameters (key or group; * allowed)
# exclude_parameters: [waves]   # or rather not these parameters
# render_mode: vectors  # initial view: raster (default), particles, vectors or wavevectors
# arrow_halo_color: "#ffffff"  # colour of the outline (halo) around the wind arrows (default white)
# particle view (contrast against the layer behind it):
# particle_color: "#0b1f3a"    # one fixed colour instead of velocity colours (high contrast, e.g. on mobile)
# particle_width: 2            # line width of the particles (default 2)
# particle_base_opacity: 0.35  # how strongly the raster underneath is dimmed (0-1; default 0.35)
# isobar layer (only meaningful if the dataset has pressure):
# show_isobars: true           # open with the isobars + pressure-centres layer on
# isobar_interval: 2           # hPa between isobars (default 4; smaller = more lines)
# isobar_levels: [1000, 1005, 1010]  # or: exactly these isobars (overrides isobar_interval)
# isobar_smoothing: 60         # smoothing of the pressure field in km (default 60; 0 = off; 100-150 = more synoptic)
# show_pressure_centres: false # hide the H/L pressure centres (default on)
# pressure_prominence: 4       # hPa an H/L must "enclose" to be shown (default = isobar_interval)
# max_pressure_centres: 3      # show at most this many H and this many L (default 4)
# center: [52.1, 5.3]
# zoom: 7
# size in a Sections dashboard:
# columns: full   # width: "full" (default) or a number of columns
# rows: 8         # height in grid rows
# units (nautical):
# wind_unit: kn        # wind + gusts: m/s (default), kn, km/h or mph
# visibility_unit: NM  # visibility: km (default) or NM (nautical miles)
# direction_unit: deg  # wind direction: compass (N/E/S/W, default) or deg (0-360°)
# detailed meteogram — rows visible by default (the rest starts hidden; empty = all):
# meteogram_parameters: [wind_10m, wind_gust_10m, temperature_2m, precipitation]
# meteogram_resolution: uur   # column time step: kwartier, uur, 3uur or dag (day = average; precipitation = sum)
# measurement_radius_km: 10   # meteogram → compare models → Measurement: radius for nearby stations
```

#### Splitting datasets over several cards

Each card picks its own datasets and parameters, so you can keep the weather and
the waves apart — two cards side by side on the same dashboard:

```yaml
# card 1: weather, without wave data
type: custom:grib-overlay-card
exclude_parameters: [waves]

# card 2: waves and swell only
type: custom:grib-overlay-card
parameters: [waves]
```

- `datasets` / `exclude_datasets` pick the **sources**: match on `source`
  (`knmi`, `dwd`, `dmi`, `rws`, `metno`, `bsh`), dataset key or name, the title
  from the dropdown, or the entry-id. `*` works as a wildcard (`dmi_*`,
  `rws_swan_*`).
- `parameters` / `exclude_parameters` pick the **parameters** within those
  sources: parameter keys (`wave_height`), wildcards (`swell_*`) or a group
  name: `waves` (every wave, swell and wind-wave parameter), `swell`,
  `windwaves`, `wind`, `sea` (current, water level, water temperature) or
  `weather`. The Dutch names (`golven`, `deining`, `windgolven`, `zee`, `weer`)
  work too.
- A direction belongs to its height/period: pick `wave_height` and
  `wave_direction` stays available for the arrows (unless you exclude it
  yourself).
- The filter applies to the whole card: the dropdown, the overlay and the
  detailed meteogram. A source with nothing left disappears from the list; if
  nothing is left at all, the card says so.

### Model-comparison card (`grib-overlay-compare-card`)

Compare, at one point, what the different sources predict. Click on the mini-map
to move the point; at the top choose the parameter and the column time step.

```yaml
type: custom:grib-overlay-compare-card
parameter: wind_10m          # initial parameter (union of all sources)
center: [52.98, 4.12]        # initial position of the mini-map (e.g. a harbour)
zoom: 9
# meteogram_resolution: 3uur # table column time step: kwartier, uur, 3uur or dag
# datasets: [knmi, dwd]      # optional: compare only these sources
#                            #   (match on source, dataset key/name, title or entry-id; * allowed)
#                            #   `entries:` / `models:` do the same (older name)
# exclude_datasets: [bsh]    # or rather not these sources
# parameters: [waves]        # only these parameters in the dropdown (key, * or group)
# exclude_parameters: [sea]  # or rather not these parameters
# measurement_radius_km: 10  # radius for "nearby measurement stations" (default 10 km)
# units work just like on the overlay card:
# wind_unit: kn
# direction_unit: deg
```

The comparison shows **all sources that have the chosen parameter** as coloured
lines + a table (row per model). Models that do not cover the point (e.g. BSH
inland) are listed at the bottom as “niet getoond” (not shown). Tick models on/off
with the checkboxes below the map. The **model names** are shown **compactly** (the
source abbreviation, e.g. `KNMI` / `DWD` / `BSH`) — in the table, the chart legend
and the checkboxes, and as the source badge in the **detailed meteogram** — so that
on a smartphone the data columns and the measurement inputs keep the room; the
**full name** is available as a tooltip. If you have **several models from the same
source** (e.g. two KNMI datasets), each gets a distinguishing suffix — a region
(`KNMI NL` / `KNMI EU`) or model name — so the difference stays clear. To decide it
yourself, set a **short alias** per source in the integration options (Configure →
*Short alias*); that is then used as the compact label everywhere.

**Measurement & delta.** Tick **“Meting invoeren”** (Enter measurement) to type a
measured value per column (in the same unit as the chart). You then get a **Δ row**
per model with the **absolute** (**measurement − model**; `+` = measurement higher)
and the **relative** (%) deviation, plus a **bias (abs + %) / MAE / RMSE** summary, and the measurement appears
as a dark line in the chart. The same measurement/delta is also in the meteogram under
**Weergave → “vergelijk modellen” → Meting** (View → compare models → Measurement).
**“Wis meting”** (Clear measurement) clears the point's saved measurement in one
click; **“Wis alle meetdata”** (Clear all measurement data) clears the measurements
of **all** saved points at once (after a confirmation; the button shows how many
points that is and is greyed out when nothing is stored). The latter solves the
case where a phone leaves you unable to clear the very last point, because a point
only disappears once you move to another one.

**Download measurement stations.** With “Meting invoeren” on, the measurement stations
within `measurement_radius_km` (default 10 km; also via the radius field) appear as
**green dots on the mini-map** and as **buttons with distance** — **only stations that
have data for the chosen parameter** (checked up front with KNMI/RWS; water/waves/current
from **RWS**, weather from **KNMI**). Click a station — or the **“Meetstation
downloaden”** button (nearest) — to **fetch its real observations** and show/store them
as the measurement, just like a hand-entered value. If a station still returns nothing,
it is hidden immediately. In the separate
compare card the point moves to the station; in the meteogram the point stays put (the
measurement then comes from the nearby station).

**Corrected forecast.** Under **“Correctie”** choose *absolute* (shift) or *relative*
(scale) and tick the **sources** to apply it to. Each ticked source gets a **corrected
row + dashed line**: its own average deviation from the measurement over the
overlapping (past) columns, carried forward across the whole forecast. If the
measurement was on average **higher** than the source, the correction moves **up**
(and vice versa).

**About the station APIs (verify).** The providers are implemented best-effort: KNMI
via the **EDR** API — `.../collections/10-minute-in-situ-meteorological-observations/locations/{id}`
(the nearest station is resolved from `/locations`; `/position` does not exist here),
with the **same KNMI Open Data key** the integration already uses and the EDR variables
`ff`/`gff`/`dd`/`ta`/`td`/`rh`/`rg`/`pp`/`zm`. RWS via the **keyless** WaterWebservices
**DDAPI20** (`ddapi20-waterwebservices.rijkswaterstaat.nl`: `OphalenCatalogus` → nearest
station → `OphalenWaarnemingen`, AQUO quantities
`Hm0`/`Tm02`/`Th0`/`STROOMSHD`+`STROOMRTG`; `Hm0` arrives in cm and is converted to m) —
the classic `_DBO` endpoints are switched off; verified live on 2026-09-16. The exact KNMI
codes/requests may differ; on a failure you now get a message in the card **and** a
`WARNING` in the HA log with the exact cause. The response parsers are covered by fixture
tests. *(Precipitation comes from KNMI as intensity `rg` in mm/h — not a direct
per-interval sum; keep that in mind.)*

> **KNMI 403 on download?** Your HARMONIE key is often **not** authorised for the
> observations dataset (KNMI then returns `403`). Create/request a key with access to
> `10-minute-in-situ-meteorological-observations` on the
> [KNMI Developer Portal](https://developer.dataplatform.knmi.nl/) and put it in the
> integration option **Observations API key** (Configure). `401` = key not recognised.

With `dataset` you choose which dataset the card shows by default on load; the value
may be the dataset key (e.g. `bsh_current_northsea`), the dataset name, or the title
as it appears in the card's picker (case-insensitive). To fix an exact config
instance instead, use `entry_id` (which wins over `dataset`). Without
`dataset`/`entry_id`/`parameter` the card automatically picks the first configured
dataset and the first selected parameter type, and you can switch within the card.

**`render_mode` — initial view.** Determines which view the card opens with (you can
always switch in the card via the view picker). Choices:

- `raster` — coloured area fill of the parameter (**default**).
- `particles` — windy.com-like animated particles over a dimmed raster; **wind
  only**. Hard to see against the layer behind it (especially on mobile)? Increase
  the contrast with `particle_color` (one fixed colour instead of the velocity
  colours — e.g. `#0b1f3a` dark or `#ffffff` white), `particle_width` (thicker
  lines) and/or `particle_base_opacity` (dim the raster further). The animation
  only costs anything while you are looking at it: Home Assistant keeps the
  cards of a dashboard page you do not have open in the page, and from 0.38.0
  the card puts itself to sleep (and the time animation with it) until you come
  back.
- `vectors` — arrows (direction + magnitude), coloured by wind speed with an
  outline; **wind only**.
- `wavevectors` — arrows for the wave direction; **waves only**. The arrows
  belong to the selected kind: waves, swell or wind waves.

If the chosen mode does not match the parameter (e.g. `vectors` while there is no
wind), the card automatically falls back to `raster`. The outline colour of the wind
arrows is set with `arrow_halo_color` (default white).

**Isobar layer.** `show_isobars: true` opens with the isobars + H/L pressure centres
as a **separate layer** on top of the chosen view (so not a `render_mode`; in the
card this is the *Isobars* checkbox). This layer appears only if the dataset has a
pressure parameter. Control which isobars are drawn with `isobar_interval` (hPa
between the lines, default 4) or `isobar_levels` (a list of exact hPa values). With
`isobar_smoothing` (km, default 60) you smooth the pressure field to synoptic scale
— that gives cleaner isobars and more reliable H/L; the same smoothed field feeds
both, so they stay consistent (0 = no smoothing, 100–150 = more synoptic).

The **H/L pressure centres** are determined as on a real weather map: a centre is
shown only if it is enclosed by at least one closed isobar (adjustable with
`pressure_prominence`, default equal to `isobar_interval`), plus a minimum mutual
distance and a maximum. That removes the many small "noise" centres. Limit them
further with `max_pressure_centres` (default 4 per type) or turn them off with
`show_pressure_centres: false`.

### Weather-map card (`grib-overlay-weathermap-card`)

```yaml
type: custom:grib-overlay-weathermap-card
# title: Weather map   # optional; default "KNMI weather map"
```

Shows KNMI's weather chart as KNMI draws it: isobars, H/L and warm, cold and
occluded fronts over Europe and the eastern Atlantic. Browse with ◀ ▶ (or swipe
on a phone) or pick a chart from the list: the latest four **analyses** (00, 06,
12 and 18 UTC, available about an hour later) and the **forecast charts** after
them, up to 48 hours ahead. The card starts at the newest analysis and refreshes
the list every 10 minutes. Times are in your own time zone, with the UTC hour
printed on the chart itself alongside.

- **Key:** the charts come from KNMI's `weather_maps` dataset and use the Open
  Data key of your KNMI integration; without a KNMI integration the card says so.
- **Storage:** Home Assistant fetches the charts and keeps them (~50 KB each) in
  the cache folder.
- **Not a map layer:** they are images in KNMI's own projection, so they are not
  laid over the other maps.

### Size / layout

In a **Sections dashboard** the card fills the full width by default and the map
height adapts to the assigned cell. You set the height/width in a Sections dashboard
the HA way:

- **Drag** the handles on the edge of the card in the dashboard editor (the most
  reliable way), or
- **In YAML with HA's own `grid_options`**:
  ```yaml
  type: custom:grib-overlay-card
  grid_options:
    rows: 10       # height in grid rows
    columns: full  # or a number of columns
  ```
  Note: the card's own `rows:`/`columns:` only apply as an *initial size* and are
  overridden by HA once a `grid_options` is saved (which happens as soon as you
  place or drag the card). So in a Sections dashboard use `grid_options` or the drag
  handles.

In a regular (**masonry**) dashboard the card's own `rows:` determines the map
height.

### Units

For nautical use the card can optionally show different units. This is purely a
display choice in the card (the underlying data does not change):

- `wind_unit`: unit for wind and gusts — `m/s` (default), `kn` (knots / nautical
  miles per hour), `km/h` or `mph`.
- `visibility_unit`: unit for visibility — `km` (default) or `NM` (nautical miles).
- `direction_unit`: display of the wind direction (in the readout under the cursor
  and on the second axis of the wind meteogram) — `compass` (`N/E/S/W`, default) or
  `deg` (numeric `0–360°`).

The legend and the label in the parameter picker are then converted automatically.

## Four example cards

Four starting points, each with exactly the YAML that produces it. Paste the YAML
into a manual card and you get what is described below it.

### Wind as particles, with isobars and pressure centres

```yaml
type: custom:grib-overlay-card
title: Wind en druk
dataset: harmonie_arome_cy43_p1
parameter: wind_10m
render_mode: particles
show_isobars: true
wind_unit: kn
center: [52.4, 4.3]
zoom: 7
```

The overlay card in its most common form: wind speed as a colour layer,
particles flowing with the wind, and the isobar layer on top with **H** and
**L** centres. Wind in knots.

### Waves, with direction arrows

```yaml
type: custom:grib-overlay-card
title: Golven en deining
parameters: [golven]
parameter: wave_height
render_mode: wavevectors
center: [53.2, 3.6]
zoom: 6
```

The same card, filtered to wave data (`parameters: [golven]`) and in
`wavevectors` mode: the arrows point the wave direction that belongs to the
chosen height.

### Model comparison at a point

```yaml
type: custom:grib-overlay-compare-card
title: Modelvergelijking
parameter: wind_10m
meteogram_resolution: 3uur
wind_unit: kn
center: [52.4, 4.5]
zoom: 8
```

Click a point on the mini map and every configured source becomes a line in the
chart and a row in the table — three models for 10 m wind here, in 3-hour
columns.

### The KNMI weather chart

```yaml
type: custom:grib-overlay-weathermap-card
title: Weerkaart
```

Analyses and forecast charts up to 48 hours ahead, with fronts, isobars and
pressure systems — the chart KNMI publishes itself.

> The examples also live in `dev/shots.html`, which renders them one by one at
> a fixed width against the mock server (`?card=overlay`, `waves`, `compare`,
> `weathermap`). A test keeps that page and the YAML above from drifting apart.
## All settings — reference

Complete, exact list of every key and value you can use in the integration
(config-flow/options) and in the card YAML. The keys are case-sensitive; use them
exactly as below.

### Sources (`source`)

| `source` | Name | API key |
| --- | --- | --- |
| `knmi` | KNMI Data Platform | yes (Open Data key) |
| `dwd` | DWD Open Data | no |
| `bsh` | BSH (North Sea current) | no |
| `dmi` | DMI Open Data | no |
| `rws` | Rijkswaterstaat (NOOS-Matroos) | no |
| `metno` | MET Norway | no |
| `noaa` | NOAA GFS (NOMADS) | no |

### Datasets (`dataset`)

| Source | `dataset` | Name | Grid | Horizon (max) | Step |
| --- | --- | --- | --- | --- | --- |
| `knmi` | `harmonie_arome_cy43_p1` | HARMONIE-AROME Cy43 — Netherlands | regular lat/lon | 60 h | 1 h |
| `knmi` | `harmonie_arome_cy43_p3` | HARMONIE-AROME Cy43 — Europe (DINI) | rotated lat/lon | 60 h | 1 h |
| `dwd` | `ewam` | DWD EWAM — European waves | regular lat/lon | 78 h | 1 h |
| `dwd` | `gwam` | DWD GWAM — global waves (cut to 30–72°N, 40°W–30°E) | regular lat/lon, 0.25° | 174 h | 3 h |
| `dwd` | `icon_d2` | DWD ICON-D2 — weather model 2.2 km | regular lat/lon | 48 h | 1 h |
| `bsh` | `bsh_current_northsea` | BSH — North Sea current | regular lat/lon | 48 h | 15 min |
| `dmi` | `dmi_wam_nsb` | DMI WAM — waves North Sea and Baltic (47–66°N, 13°W–30°E, ~5 km) | regular lat/lon | 132 h | 1 h |
| `dmi` | `dmi_wam_natlant` | DMI WAM — waves North Atlantic (30–78°N, 69°W–30°E, 0.25°) | regular lat/lon | 132 h | 1 h |
| `dmi` | `dmi_dkss_nsbs` | DMI DKSS — currents and water level (48.5–65.9°N, from 4.1°W, ~5 km) | regular lat/lon | 120 h | 1 h |
| `rws` | `rws_dcsm` | RWS DCSM — currents and water level (43–64°N, 12°W–13°E, 0.05°) | regular lat/lon | 48 h | 1 h |
| `rws` | `rws_dcsm_zuno` | RWS DCSM-ZUNO — currents and water level southern North Sea (49.4–57°N, 3.4°W–9.6°E, 0.025°) | regular lat/lon | 48 h | 1 h |
| `rws` | `rws_swan_dcsm` | RWS SWAN — waves North Sea and Channel (48–64°N, 12°W–9°E, 0.05°) | regular lat/lon | 48 h | 1 h |
| `rws` | `rws_swan_kuststrook` | RWS SWAN — waves Dutch coast (51–54.4°N, 0.02°) | regular lat/lon | 48 h | 1 h |
| `metno` | `metno_oslofjord` | MET Norway — Oslofjord (58.9–60.0°N, 9.8–11.2°E) | regular lat/lon, 0.05° | 66–120 h | 1 h |
| `metno` | `metno_skagerrak` | MET Norway — Skagerrak (57.7–59.4°N, 7.8–12.0°E) | regular lat/lon, 0.05° | 66–120 h | 1 h |
| `metno` | `metno_sorlandet` | MET Norway — Sørlandet (57.8–58.8°N, 7.0–9.4°E) | regular lat/lon, 0.05° | 66–120 h | 1 h |
| `noaa` | `gfs` | NOAA GFS — global model (cut to 40–65°N, 25°W–15°E) | regular lat/lon, 0.25° | 384 h | 1 h (≤120 h), 3 h after |
| `noaa` | `gfs_wave` | NOAA GFS-Wave — global waves (same window) | regular lat/lon, 0.25° | 384 h | 1 h (≤120 h), 3 h after |

### Parameters (`parameter` / `parameters`)

**KNMI** (`harmonie_arome_cy43_p1` and `harmonie_arome_cy43_p3`, identical):

| `parameter` | Name | Unit | Type |
| --- | --- | --- | --- |
| `wind_10m` | Wind (10m) | m/s | vector |
| `wind_gust_10m` | Gusts (10m) | m/s | vector |
| `temperature_2m` | Temperature (2m) | °C | scalar |
| `dewpoint_2m` | Dew point (2m) | °C | scalar |
| `humidity_2m` | Relative humidity (2m) | % | scalar |
| `precipitation` | Precipitation | mm | scalar |
| `pressure_msl` | Pressure (mean sea level) | hPa | scalar |
| `visibility` | Visibility | km | scalar |
| `cloud_cover` | Cloud cover | % | scalar |

**DWD** (`ewam` and `gwam`, identical):

| `parameter` | Name | Unit | Type |
| --- | --- | --- | --- |
| `wave_height` | Wave height (significant) | m | scalar |
| `wave_period` | Wave period (mean) | s | scalar |
| `wave_direction` | Wave direction (mean) | ° | scalar |
| `swell_height` | Swell: height | m | scalar |
| `swell_period` | Swell: period (mean) | s | scalar |
| `swell_peak_period` | Swell: peak period | s | scalar |
| `swell_direction` | Swell: direction | ° | scalar |
| `wind_wave_height` | Wind waves: height | m | scalar |
| `wind_wave_period` | Wind waves: period (mean) | s | scalar |
| `wind_wave_peak_period` | Wind waves: peak period | s | scalar |
| `wind_wave_direction` | Wind waves: direction | ° | scalar |

**DWD** (`icon_d2`) — the same keys as KNMI, so the model comparison puts them
side by side:

| `parameter` | Name | Unit | Type |
| --- | --- | --- | --- |
| `wind_10m` | Wind (10 m) | m/s | vector |
| `wind_gust_10m` | Wind gusts (10 m) | m/s | scalar (speed only) |
| `temperature_2m` | Temperature (2 m) | °C | scalar |
| `dewpoint_2m` | Dew point (2 m) | °C | scalar |
| `humidity_2m` | Relative humidity (2 m) | % | scalar |
| `precipitation` | Precipitation (per hour) | mm | scalar |
| `pressure_msl` | Pressure (mean sea level) | hPa | scalar |
| `visibility` | Visibility | km | scalar |
| `cloud_cover` | Cloud cover | % | scalar |
| `cape` | CAPE (thunderstorm energy) | J/kg | scalar |

ICON-D2 delivers precipitation as a total since the start of the run; the
integration converts it to the amount per hour, as with KNMI. ICON's gusts are the
maximum of the past hour, without a direction of their own. At a run's start time
(+0 h) neither exists yet, so those two have no image there.

**DMI** (`dmi_wam_nsb` and `dmi_wam_natlant`) — the same keys as EWAM:

| `parameter` | Name | Unit | Type |
| --- | --- | --- | --- |
| `wave_height` | Wave height (significant) | m | scalar |
| `wave_period` | Wave period (mean) | s | scalar |
| `wave_peak_period` | Waves: peak period | s | scalar |
| `wave_direction` | Wave direction (mean) | ° | scalar |
| `swell_height`, `swell_period`, `swell_direction` | Swell: height, period, direction | m, s, ° | scalar |
| `wind_wave_height`, `wind_wave_period`, `wind_wave_direction` | Wind waves: height, period, direction | m, s, ° | scalar |

**DMI** (`dmi_dkss_nsbs`):

| `parameter` | Name | Unit | Type |
| --- | --- | --- | --- |
| `current` | Sea current (surface) | m/s | vector |
| `water_level` | Water level | m | scalar |
| `water_temperature` | Water temperature | °C | scalar |

**RWS** (`rws_dcsm` and `rws_dcsm_zuno`, identical):

| `parameter` | Name | Unit | Type |
| --- | --- | --- | --- |
| `current` | Sea current (surface) | m/s | vector |
| `water_level` | Water level | m | scalar |

**RWS** (`rws_swan_dcsm` and `rws_swan_kuststrook`):

| `parameter` | Name | Unit | Type |
| --- | --- | --- | --- |
| `wave_height` | Wave height (significant, Hm0) | m | scalar |
| `wave_period` | Wave period (mean, Tm-1,0) | s | scalar |
| `wave_direction` | Wave direction (mean, Th0) | ° | scalar |

**MET Norway** (`metno_oslofjord`, `metno_skagerrak`, `metno_sorlandet`):

| `parameter` | Name | Unit | Type | Model, ahead |
| --- | --- | --- | --- | --- |
| `wind_10m` | Wind (10 m) | m/s | vector | MEPS, ~66 h |
| `precipitation` | Precipitation (per hour) | mm | scalar | MEPS, ~66 h |
| `pressure_msl` | Pressure (mean sea level) | hPa | scalar | MEPS, ~66 h |
| `wave_height` | Wave height (significant) | m | scalar | WAVEWATCH III 4 km, ~72 h |
| `wave_direction` | Wave direction (mean) | ° | scalar | WAVEWATCH III 4 km, ~72 h |
| `current` | Sea current (3 m deep) | m/s | vector | NorKyst 800 m, ~120 h |

**NOAA** (`gfs`) — the same keys as KNMI and ICON-D2:

| `parameter` | Name | Unit | Type |
| --- | --- | --- | --- |
| `wind_10m` | Wind (10m) | m/s | vector |
| `wind_gust_10m` | Gusts (10m) | m/s | scalar (speed only) |
| `temperature_2m` | Temperature (2m) | °C | scalar |
| `dewpoint_2m` | Dew point (2m) | °C | scalar |
| `humidity_2m` | Relative humidity (2m) | % | scalar |
| `precipitation` | Precipitation (rate) | mm/h | scalar |
| `pressure_msl` | Pressure (mean sea level) | hPa | scalar |
| `visibility` | Visibility | km | scalar |
| `cloud_cover` | Cloud cover | % | scalar |
| `cape` | CAPE (thunderstorm energy) | J/kg | scalar |

Mind the precipitation: KNMI and ICON-D2 give an **amount per hour** (mm), GFS
the **rate at that moment** (mm/h). GFS restarts its precipitation total every
six hours, so subtracting consecutive totals would lose the hour straddling each
restart; the instantaneous rate does not have that problem. In the comparison
they sit side by side but are not the same number.

**NOAA** (`gfs_wave`) — the same keys as EWAM and DMI:

| `parameter` | Name | Unit | Type |
| --- | --- | --- | --- |
| `wave_height` | Wave height (significant) | m | scalar |
| `wave_peak_period` | Waves: peak period | s | scalar |
| `wave_direction` | Wave direction (dominant wave) | ° | scalar |
| `swell_height`, `swell_period`, `swell_direction` | Swell: height, period, direction | m, s, ° | scalar |
| `wind_wave_height`, `wind_wave_period`, `wind_wave_direction` | Wind waves: height, period, direction | m, s, ° | scalar |
| `wind_10m` | Wind (10m) | m/s | vector |

GFS-Wave publishes the period and direction of the **dominant** wave, where EWAM
and DMI give a mean over the whole spectrum; hence `wave_peak_period` rather
than `wave_period`. Swell arrives in partitions (ordered by energy); the
integration shows the first, the dominant swell train. The wind parameter is the
wind the wave model was driven with, so sea state and the wind over it come from
the same file.

**BSH** (`bsh_current_northsea`):

| `parameter` | Name | Unit | Type |
| --- | --- | --- | --- |
| `current` | Sea current (surface) | m/s | vector |

The **type** determines which views are available: `vector` parameters
(`wind_10m`, KNMI's `wind_gust_10m`, `current`) support `particles`/`vectors`; a
direction parameter (unit °, e.g. `wave_direction`) enables `wavevectors`; and
`pressure_msl` (unit hPa) enables the isobar layer. A direction belongs to the
height and period with the same prefix: `swell_direction` goes with
`swell_height`, `swell_period` and `swell_peak_period`. When you switch swell on,
include `swell_direction` too, or the swell rows have no arrows.

### Integration: setup fields (config flow)

| Key | Values |
| --- | --- |
| `source` | `knmi`, `dwd`, `bsh`, `dmi`, `rws`, `metno` or `noaa` |
| `api_key` | KNMI Open Data key (leave empty for DWD/BSH) |
| `notification_api_key` | optional; **separate** KNMI Notification Service key (empty, or your Open Data key = polling only) |
| `dataset` | a dataset key from the table above |
| `parameters` | list of parameter keys you want to keep up to date (can be changed later in the options) |

### Integration: options (Configure)

| Key | Type | Default | Range / form |
| --- | --- | --- | --- |
| `parameters` | list | the choice made when adding | which parameters of the dataset are downloaded and shown. A parameter you switch on appears once the current run has been processed again; that starts right after saving |
| `forecast_horizon_hours` | number (hours) | `24` | From 1 to however far the dataset itself reaches (60 for HARMONIE, 78 for EWAM, 174 for GWAM, 384 for GFS). Making it longer processes the current run again right away; shorter cuts the run already processed |
| `retain_runs` | integer | `2` | 1–10 |
| `update_interval_minutes` | integer (min) | `30` | 5–180 |
| `notification_api_key` | text | (empty) | **separate** KNMI Notification Service key for push. Not your Open Data key: the broker refuses that with `Not authorized`. Empty = polling only, no MQTT attempt |
| `observations_api_key` | text | (empty) | KNMI Open Data key with access to `10-minute-in-situ-meteorological-observations`, for **downloading station observations**. Your HARMONIE key is often not authorised for it (KNMI returns 403). Empty = reuse the HARMONIE key |
| `alias` | text | (empty) | **short name** for this source, shown as the compact label in the comparison and meteogram (e.g. `KNMI NL`). Empty = derived automatically from the source (same-source entries are disambiguated automatically) |
| `storage_path` | text | (empty) | **folder for the working files** (run archive, extracted files, rendered cache). Empty = `/var/tmp/grib_overlay`: in no backup, and emptied by an HA update (everything is then downloaded again). **Never** point this into a folder your backup includes (see [Backups](#backups)) |
| `color_scales` | multi-line text | (empty) | per line: `parameter: value:#hex, value:#hex, …` (values in the parameter's **own unit**) |

### Card settings (Lovelace YAML)

| Key | Type | Default | Values / meaning |
| --- | --- | --- | --- |
| `dataset` | text | (first) | dataset key, name or title — which dataset on load |
| `entry_id` | text | (first) | exact config entry id (wins over `dataset`) |
| `parameter` | text | (first) | parameter key — which parameter on load |
| `datasets` | list or text | — | only these sources on this card; match on `source`, dataset key/name, title or entry-id, `*` as a wildcard. Empty = all |
| `exclude_datasets` | list or text | — | rather **not** these sources (same matching) |
| `parameters` | list or text | — | only these parameters: key, wildcard or group (`waves`, `swell`, `windwaves`, `wind`, `sea`, `weather`). Empty = all |
| `exclude_parameters` | list or text | — | rather **not** these parameters (e.g. `[waves]` for a weather card without wave data) |
| `render_mode` | text | `raster` | `raster`, `particles`, `vectors`, `wavevectors` (falls back to `raster` if the parameter does not support it) |
| `arrow_halo_color` | hex colour | `#ffffff` | outline (halo) around the wind arrows |
| `particle_color` | hex colour | (velocity colours) | one fixed particle colour for high contrast |
| `particle_width` | number | `2` | line width of the particles |
| `particle_base_opacity` | number `0`–`1` | `0.35` | dimming of the raster under the particles |
| `show_isobars` | bool | `false` | isobars + H/L pressure centres as a separate layer |
| `isobar_interval` | number (hPa) | `4` | distance between isobars |
| `isobar_levels` | list of numbers (hPa) | — | exact isobars (overrides `isobar_interval`) |
| `isobar_smoothing` | number (km) | `60` | smoothing of the pressure field (`0` = off) |
| `show_pressure_centres` | bool | `true` | show H/L pressure centres |
| `pressure_prominence` | number (hPa) | = `isobar_interval` | enclosure threshold for an H/L |
| `max_pressure_centres` | integer | `4` | max. number of H and L |
| `center` | `[lat, lon]` | `[52.1, 5.3]` | initial position of the map |
| `zoom` | number | `7` | initial zoom level |
| `base_map` | text | `osm` | initial base map: `osm` (OpenStreetMap) or `emodnet` (EMODnet bathymetry), see [Map layers](#map-layers) |
| `map_layers` | list or text | `[seamarks]` | layers switched on: `seamarks`, `sport`, `depth`, `soundings`, `gebco` |
| `tile_url` | text | (empty) | your own tile server instead of OpenStreetMap, as a Leaflet template (`https://…/{z}/{x}/{y}.png`) |
| `tile_attribution` | text (HTML) | OpenStreetMap | attribution for `tile_url` |
| `columns` | `full` or number | `full` | width in a Sections dashboard |
| `rows` | number | — | height in grid rows (masonry) / initial size |
| `grid_options` | object | — | HA-native `{rows, columns}` (wins over `rows`/`columns`) |
| `wind_unit` | text | `m/s` | `m/s`, `kn`, `km/h`, `mph` |
| `visibility_unit` | text | `km` | `km`, `NM` |
| `direction_unit` | text | `compass` | `compass`, `deg` |
| `meteogram_parameters` | list or text | — | parameter keys that are **visible by default** in the detailed meteogram; the rest starts hidden (enable via the chips). Empty = show all rows. Match on parameter key, so it applies to all sources |
| `meteogram_resolution` | text | `uur` | time step of the meteogram columns: `kwartier`, `uur`, `3uur` or `dag`. For `dag` the daily average (precipitation: daily sum); finer = value at that time. Also switchable via “Kolommen” in the window itself |

The card's dropdown does **not** offer directions as layers of their own (wave
direction, swell direction): a direction belongs to its height or period and is
drawn on top of it as arrows. To have one as a colour layer anyway, name it
explicitly with `parameter: wave_direction`.

`datasets`/`parameters` (and their `exclude_` variants) apply to the whole card:
dropdown, overlay and the detailed meteogram. A direction parameter stays as
long as its height/period does (`wave_height` keeps `wave_direction`), so the
arrows keep working. See
[Splitting datasets over several cards](#splitting-datasets-over-several-cards).

The old spelling `renderMode` (camelCase) also keeps working alongside
`render_mode`. `meteogram_parameters` may be either a YAML list or a
comma/space-separated string; e.g. `[wind_10m, wind_gust_10m, temperature_2m]` or
`"wind_10m, wind_gust_10m, temperature_2m"`. The hidden/visible choice you make
afterwards in the meteogram itself (tapping a row label, chips, “Alle rijen tonen”)
applies temporarily, for that opened window.

### Model-comparison card (`grib-overlay-compare-card`)

| Key | Type | Default | Values / meaning |
| --- | --- | --- | --- |
| `parameter` | text | (first) | initial parameter being compared (union of all sources) |
| `center` | `[lat, lon]` | `[52.1, 5.3]` | initial position of the mini-map |
| `zoom` | number | `7` | initial zoom level of the mini-map |
| `base_map`, `map_layers`, `tile_url`, `tile_attribution` | | | map layers, as for the overlay card |
| `datasets` (or `entries`/`models`) | list or text | — | compare only these sources; match on `source`, dataset key/name, title or entry-id, `*` as a wildcard. Empty = all sources that have the parameter |
| `exclude_datasets` | list or text | — | rather **not** these sources |
| `parameters` / `exclude_parameters` | list or text | — | which parameters the dropdown offers: key, wildcard or group (`waves`, `sea`, `weather` …) |
| `meteogram_resolution` | text | `uur` | column time step of the table: `kwartier`, `uur`, `3uur`, `dag` |
| (no key) | | | the parameter list follows the **ticked** models: untick a source and the parameters only that source has disappear |
| `wind_unit`, `visibility_unit`, `direction_unit` | text | see below | same unit options as the overlay card |

### Weather-map card (`grib-overlay-weathermap-card`)

| Key | Type | Default | Values / meaning |
| --- | --- | --- | --- |
| `title` | text | `KNMI weather map` | card heading |

### Units (valid values + aliases)

- **`wind_unit`** — applies to all m/s parameters (wind, gusts, sea current): `m/s`
  (default), `kn` (knots; also `kt`, `kts`, `knots`, `knopen`, `knoop`), `km/h`
  (also `km/u`, `kmh`, `kph`), `mph`.
- **`visibility_unit`** — applies to `visibility`: `km` (default), `NM` (nautical
  miles; also `nm`, `zeemijl`, `zeemijlen`).
- **`direction_unit`** — wind direction in the readout and on the meteogram axis:
  `compass` (`N/E/S/W`, default), `deg` (`0–360°`; also `degrees`, `graden`, `360`,
  `0-360`, `°`).

Units are purely a display choice in the card (the underlying data and the colour
scale do not change; only the legend numbers and labels).

### Map layers

Both maps have a **layer button** in the top-right corner, with the same
nautical layers as [map.openseamap.org](https://map.openseamap.org):

| Layer | `id` | What | Source |
| --- | --- | --- | --- |
| OpenStreetMap | `osm` | base map (default) | OpenStreetMap |
| EMODnet bathymetry | `emodnet` | base map: relief of land and seabed, European seas | EMODnet Bathymetry |
| Seamarks | `seamarks` | buoys, beacons, lights, fairways (on by default) | OpenSeaMap |
| Sport | `sport` | marinas, surfing, diving and sailing spots | OpenSeaMap |
| Depth contours | `depth` | depth contours from users' soundings (beta, not everywhere) | OpenSeaMap |
| Depth soundings | `soundings` | measured depth along sailed tracks, as coloured dots | OpenSeaMap |
| GEBCO depth | `gebco` | worldwide depth shading of the sea, semi-transparent | GEBCO 2021 via OpenSeaMap |

`base_map` and `map_layers` choose what a card starts with. Whatever you click in
the layer button afterwards is remembered by the browser for both cards, and then
takes precedence over the card settings.

```yaml
type: custom:grib-overlay-card
base_map: emodnet
map_layers: [seamarks, soundings, gebco]
```

These are aids, not an official nautical chart: do not use them for navigation.

#### OpenStreetMap and "Access blocked"

OpenStreetMap runs on volunteer servers and, since September 2026, blocks apps that
don't follow its [tile usage policy](https://operations.osmfoundation.org/policies/tiles/):
you then see tiles saying **"Access blocked"**. So:

- **Home Assistant 2026.9 and newer:** the tiles come through Home Assistant
  itself (`/api/map_tiles`, like Home Assistant's own maps). Home Assistant
  fetches them under its own name and keeps them for a week; the card asks for a
  short-lived token for that and renews it by itself.
- **Older Home Assistant:** the card goes to `https://tile.openstreetmap.org`
  directly and sends the required `Referer` (only your Home Assistant's address,
  not the dashboard path).
- **Your own tile server:** set `tile_url` (and `tile_attribution`) on the card;
  it replaces OpenStreetMap in the layer button.

## Performance

What the integration does to stay light, and what you get out of it. The
numbers below were measured on a real instance with **fourteen** configured
sources.

- **The heavy grids travel compressed.** One wind frame is over 200 kB of
  numbers written out as text — the biggest thing the card ever downloads — and
  about **four times** smaller gzipped. The compressed copy is written beside
  the file the first time a frame is asked for and goes away with the run it
  belongs to, so there is no work per request.
- **The lists travel compressed too.** One source's frame list is 49 kB of
  timestamps and urls; it is built in memory, so there is no compressed copy
  beside it — it is gzipped on the way out. Short answers are left alone: below
  a few kB the header costs more than it saves.
- **The next frame is only fetched ahead when you will want it** — while the
  animation is playing, and from the moment you move through time yourself. On
  a page that is only being looked at, that saves a second map image of well
  over 100 kB that nobody ever sees.
- **A dashboard page fetches nothing twice.** The card's caches hold the
  *request*, not the answer, so two parts of the card asking for the same frame
  at the same moment now wait on one fetch. And every card on a page shares one
  list of configured sources instead of each fetching its own.
- **The chart card shows what it has.** Listing KNMI's charts and fetching them
  takes a couple of seconds, and the charts change every few hours — so you get
  the list that is already there at once and the new one is fetched behind it.
  Only a card with nothing at all to show waits.
- **Every source has its own moment.** Home Assistant starts them all within
  the same second, so without more, fourteen sources would download and decode
  on the same second of every half hour. Each one now waits out its own slot in
  the interval, derived from its id, so it is the same slot after every restart.
- **Cards you cannot see do nothing.** The particle animation and the time
  animation sleep while the card is off screen, and the chart card skips its
  ten-minute poll for a page nobody has open.

## Keys & troubleshooting

KNMI uses **three separate keys**. They are not interchangeable; a key in the
wrong field is refused.

| Option | What it is for | Without it |
| --- | --- | --- |
| **API key** (Open Data) | fetching the forecast runs themselves | the integration does not work |
| **Notification Service API key** | push over MQTT, the moment a run appears | polling only — nothing else |
| **Observations API key** | downloading station observations in the comparison | no measurement stations |

What you will see in the log (Settings → System → Logs):

- **`the API key was rejected`** — the **Open Data key** is wrong and this source
  will no longer update. The message says which of the two cases it is: `401` =
  the key is not recognised at all (typo, truncated paste, expired or revoked);
  `403` = the key is recognised but has **no access to this dataset**. Logged
  once rather than on every poll; when it works again you get
  `the API key is accepted again`.
- **`KNMI Notification Service rejected the connection`** — the **Notification
  Service key** is wrong. Polling carries on, so this is not urgent. With the
  notification field empty (or holding your Open Data key, which amounts to the
  same thing) no connection is attempted and nothing is logged.
- **`Connected to the KNMI Notification Service`** — push works. This is an
  `INFO` line, so it shows up without turning on debug logging: it lets you
  confirm the notification key is right instead of guessing.
- **`KNMI EDR /locations HTTP 401/403`** — the **observations key**. Only the
  measurement stations stop working; the rest of the map carries on.
- **`KNMI weather charts unavailable`** — the KNMI weather map could not be
  fetched; the message says why (e.g. a refused key). The rest of the
  integration carries on.
- **Map tiles saying "Access blocked"** — the base map; see [Map layers](#map-layers).
  Update to 0.29.1 or newer and reload the dashboard (the browser keeps the
  blocked tiles for a while).
- **A card on another dashboard page shows the whole world with a speck of
  overlay (or looks empty)** — that card was built while its page was still
  hidden, so the dataset was fitted into a map with no size and Leaflet landed
  on zoom 0. Since 0.37.7 the card waits with that fit until it actually has a
  size, and performs it as soon as you open the page.
- **The map and overlay stay empty after switching dashboards while the rest of
  the card works** — Leaflet sometimes comes back with nothing painted. Since
  0.37.5 the card re-measures itself a few times and, if need be, builds the map
  again at the same place and moment; the overlay image is recreated when its
  image is no longer on the map.
- **The map stays empty when you browse between dashboard pages** — Home
  Assistant keeps a page's cards in memory and re-attaches them when you come
  back. Since 0.37.3 the card fetches its frames again on that re-attach,
  re-measures the map and shows the same moment as before — no page reload
  needed.
- **One parameter stays empty while the rest of the source works** — the log
  then says `Run … : no data for <parameter>`. That run is processed once more
  (on a restart or a reload of the integration); if it stays empty, it is that
  run, and the next one fills it again.
- **The isobars are on but nothing appears** — the card then says *"No pressure
  data for this time"* under the map. Either the run has not been processed yet
  (give it a moment), or pressure was only just enabled: the integration fetches
  that run again at the next poll. The browser console carries a line with the
  parameter and the time.
- **The “Isobars” checkbox is greyed out** — this source has no pressure in
  this card. Enable `pressure_msl` under Settings → Devices & services → GRIB
  Weather Overlay → Configure, and check that you are not filtering it out with
  `parameters`/`exclude_parameters`. The isobars are always drawn from the
  pressure of the **dataset being shown**, so another source that has pressure
  does not help. The checkbox's tooltip says so too.
- **Which version is the browser running, and how did it arrive?** The card
  announces itself in the browser console:
  `GRIB-OVERLAY-CARD 0.37.8 loaded in 5 ms (from cache)`. That line runs last in
  the file: if it is missing, the file was not (fully) loaded and a
  "configuration error" comes from that. If it is there, the timing says whether
  the file came from the browser's cache or had to travel.
- **The map area is zero pixels high** (0.40.1) — Leaflet writes `position:
  relative` straight onto the map div as soon as it reads that div's position as
  `static`, which is what an element reports while it is not in the page yet:
  exactly the state of a card Home Assistant is assembling during a dashboard
  switch. That inline style beats our own `position: absolute; inset: 0`, so
  `inset` stops doing anything and the map collapses to nothing — the card is
  there, the controls work, the map area is empty, and it stays that way until
  the page is reloaded. The card now hands the element back to its own
  stylesheet, as soon as Leaflet is done with it and every time it comes back on
  screen.
- **The card is there, but the map and the overlay are empty** — usually after
  switching to another dashboard: Leaflet drops the tiles of a map taken out of
  the page, and re-measuring alone does not bring them back. Every
  card (the model comparison included) checks its own map the moment it comes
  back on screen and draws it again — with a fresh attempt on *every* return,
  not twice per browser session. From 0.39.0 only what the browser actually
  painted counts: Leaflet keeps every tile invisible until its image has
  arrived, so a map whose tile requests were aborted (what a browser does to a
  part of the page that goes away — Chromium most eagerly) was full of tiles and
  completely blank, and used to pass for healthy. If it stays empty, the card
  says so itself, in the log and as a notification, with the container's size.
- **Red blocks where *all* the GRIB cards should be, only after a refresh, only
  in Chromium browsers (Vivaldi, Edge, Chrome)** — fixed in 0.40.0. Home
  Assistant puts this file in the page as a `<script type="module">`, so the
  browser runs it beside the frontend's own bundle. On a refresh it comes from
  the service worker's cache and finishes first — and that bundle then
  *replaces* `window.customElements` with its own, empty registry, which has
  never heard of an element registered before it arrived. The cards are
  perfectly fine (`document.createElement("grib-overlay-card")` returns the
  right class), but `customElements.get(...)` — exactly the question Home
  Assistant asks before building a card — answers "no such element", and you get
  a red block. From 0.40.0 the card tells that new registry about its own three
  names (nothing else is touched) and asks Home Assistant to build the card
  again. Usually that happens inside the two seconds HA waits, so the red block
  is never drawn.
- **“Configuration error” with no text under it** — Home Assistant replaces a
  card with that empty block when assigning `hass`, `preview` or `layout` to the
  card throws. Right before it does, it writes a console line with the card type
  and the error. **From 0.38.0 you do not have to be there to catch it:** the
  card reads that line itself and posts it to the integration. Home Assistant
  then shows a notification ("the card failed in the browser") with the error in
  it, and the same text is in the log (Settings → System → Logs). It also says
  whether the page was loaded or **reloaded**, which browser it was, and whether
  more than one copy of the card file is loaded. From 0.39.0 the card also goes
  **looking** for such a block on the page itself — which works even when
  another card has taken the console over — and names the other cards showing
  one. The same failure is reported
  once every five minutes, so a card that keeps failing cannot fill the log.
- **“Configuration error” where the card should be** — Home Assistant waits only
  a couple of seconds for a custom card to register itself; if the browser does
  not have the card by then (slow or mobile connection, many custom cards at
  once) that message appears, and a refresh brings the card back. From 0.36.1
  everything in the `www` folder is served **gzipped** and **cached for a
  month** — the URL carries the version, so after an update the browser fetches
  the new file by itself. If the line under “Configuration error” says something
  else (an unknown key, for instance), it is about the card's own YAML.

Need more detail? Add to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.grib_overlay: debug
```

## Language

The cards and the integration speak **the language the Home Assistant user chose
for themselves** (Profile → Language). **Dutch** and **English** ship; any other
language falls back to English. There is nothing to configure — the card reads
`hass.locale.language`.

What follows the language:

| | Dutch example | English example |
| --- | --- | --- |
| Buttons, labels, tooltips | “Wis meting”, “Meetstations binnen 10 km:” | “Clear measurement”, “Stations within 10 km:” |
| Messages and errors | “Geen model heeft data voor deze parameter op dit punt.” | “No model has data for this parameter at this point.” |
| Parameter names | Windstoten (10m), Luchtdruk (zeeniveau) | Wind gusts (10 m), Pressure (mean sea level) |
| Dataset names | HARMONIE-AROME Cy43 - **Nederland** … | HARMONIE-AROME Cy43 - **Netherlands** … |
| Wind direction (compass) | `N/NO/O/ZO/Z/ZW/W/NW` | `N/NE/E/SE/S/SW/W/NW` |
| Dates and times in chart and table | `za 05-09, 06:00` | `Sat 05/09, 06:00` |
| Word-shaped units | `km/u`, `zeemijl` | `km/h`, `nmi` |

Two caveats:

- **The config and options flow** follows the *instance* language (Settings →
  System → General) rather than the individual user's: a config flow has no
  access to the user's own language. In practice that is the same language. The
  field names themselves come from Home Assistant's own translation files
  (`translations/nl.json`, `translations/en.json`); the dataset and parameter
  lists are fetched from the provider at runtime and are therefore translated by
  the integration itself.
- **Station and place names** (Schiphol, Hoek van Holland, K13-A) are left
  alone — they are proper nouns.

Adding a language means: a block in `GRIB_TEXT`, `GRIB_PARAM_NAMES`,
`GRIB_DATASET_NAMES` and `GRIB_COMPASS` in `grib-overlay-card.js`, plus
`labels.py` and a `translations/<language>.json`.

## Backups

**The integration writes nothing into a folder a backup can include.** All
working files — run archives, extracted GRIB files and the rendered PNG/JSON
cache — can be downloaded again and don't belong in a backup:

| What | Default location |
| --- | --- |
| **Cache** (rendered images per run) | `/var/tmp/grib_overlay/<entry>/…` |
| **Working files during a download** | `/var/tmp/grib_overlay/.raw/<entry>/…` |
| **KNMI weather charts** | `/var/tmp/grib_overlay/weather_maps/` |

Why that matters:

- **Size.** With a handful of sources the cache easily reaches 1–2 GB, and map
  images hardly compress.
- **Reliability.** If a file disappears right between "backup takes inventory"
  and "backup writes", the **whole** backup fails with `FileNotFoundError`, and
  this integration removes files all the time.

`/config` always goes into a backup, and `/share` and `/media` when you tick them
in the backup settings; Supervisor cannot exclude a single directory. So the only
lever is location. Inside the Home Assistant container `/var/tmp` is plain disk,
and it is in no backup folder.

**Consequence:** a Home Assistant update recreates the container, which empties
`/var/tmp`. The integration then simply downloads everything again on the next
poll; until then the maps are empty. A normal restart keeps the cache.

Why not `/tmp`? On HAOS that is a *tmpfs* (RAM), and a ~850MB archive does not
belong in memory.

The **Working files folder** option lets you pick your own path (cache and
working files then go there). Never point it inside `/config`, nor into `/share`
or `/media` if your backup includes them.

Also:

- **Automatic cleanup on upgrade.** Older versions kept the cache in
  `/config/grib_overlay` (up to v0.25) and `/share/grib_overlay` (v0.26–v0.34). On
  the first start after the update those folders are removed — not while a
  backup is running — and your next backup is smaller straight away. Look for the
  `WARNING` in the log. A folder you set yourself as **Working files folder**
  stays.
- **Raw downloads kept apart.** The archive and the extracted files live beside
  the run directories, so cleaning up old runs never touches an in-flight
  download.
- **Pause during the backup.** Via HA's backup platform the integration pauses
  processing and cleaning up runs while a backup runs: a safety net for the
  cleanup above, and for anyone who deliberately puts the folder in a backup
  folder.

## Known limitations

- One HARMONIE forecast run from KNMI is a tar archive of ~850MB (all lead times
  together). There is no API to download individual lead times, so a **new** run
  costs that full download (a few minutes); only the lead times within the
  configured forecast horizon are decoded and kept as PNG, the rest is deleted
  again immediately. Do not set the horizon higher than needed. On a **restart**
  the already-processed run is reused from disk (no new download), and any download
  of a newer run happens in the background — the integration is available
  immediately after start with the already-cached images.
- Supported datasets: `harmonie_arome_cy43_p1` (Netherlands, regular lat-lon) and
  `harmonie_arome_cy43_p3` (Europe/DINI domain, deterministic). The latter is on a
  **rotated lat-lon grid** and is projected to a regular geographic grid during
  decoding (including rotating the wind u/v components to true north/east). The
  Europe domain is larger, so download and processing take more time/memory than
  the Netherlands — do not set the forecast horizon higher than needed.
- The **ensemble** variant `harmonie_arome_cy43_p4a` (EPS) is not supported yet;
  that requires a choice/aggregation over the ensemble members.
- From **DWD Open Data** the wave models **EWAM** and **GWAM** and the weather
  model **ICON-D2** are supported. They use simple GRIB2 packing and are
  therefore readable without a binary library. ICON-EU and ECMWF are not: they
  use CCSDS/AEC compression, which does need such a library. The coastal wave
  model CWAM is readable but starts only at 6.2°E — east of Ameland — and is
  therefore not offered (yet).
- **GWAM** is published on the whole global grid (1440 × 699 points). The
  integration cuts a fixed window out of it while decoding — **30–72°N,
  40°W–30°E**, from the latitude of the Canaries to well north of Norway and
  from mid-Atlantic to the Baltic. That is not a saving: the wind and field
  endpoints thin a grid down to a fixed number of points per axis, so a world
  field would arrive over the North Sea far coarser than the model is. The
  window is fixed and not configurable.
- **NOAA GFS and GFS-Wave** go through NCEP's NOMADS *filter* service, not
  through the raw files. That is a requirement, not an optimisation: the files
  on NCEP's own servers use complex packing with spatial differencing (template
  5.3), which the decoder here does not read — the filter service re-packs your
  selection with simple packing. The same service cuts out a window server-side,
  so one lead time with *every* parameter is a few hundred kilobytes instead of
  hundreds of megabytes. The window is fixed at **40–65°N, 25°W–15°E**. One
  request per lead time goes to NOMADS (all enabled parameters at once), at most
  two at a time: it is a free public service.
- **GFS runs** appear lead time by lead time, starting about 3 h 20 min after
  the run time; +384 hours is hours behind that. Before anything is downloaded
  the integration asks, with a single request for a single grid cell, whether
  the *last* lead time your horizon needs is online. If it is not, it waits for
  the next poll and you keep the previous run in the meantime. So the longer
  your horizon, the later a new run arrives — that is not a fault, and it is
  only noted in the debug log.
- **DCSM-ZUNO** is the same Rijkswaterstaat model as `rws_dcsm`, but the nest
  for the southern North Sea: a smaller area, asked for twice as finely (0.025°
  instead of 0.05°). About 0.8 MB per hour, so ~20 MB for a 24-hour run. Running
  both means asking the same model for the same water twice — usually you only
  want the nest.
- **ICON-D2** is a separate file of ~1 MB per parameter per hour. With all 10
  parameters and the default 24-hour horizon a run is therefore a ~250 MB download
  (48 hours: ~500 MB). A new run appears every 3 hours, about 80 minutes after
  its run time. The integration only picks a run up (for EWAM too, which takes
  ~35 minutes to publish one) once it is complete on the server. Switch on only the parameters you use, or raise the polling interval.
- **BSH sea current** is 15-minute data: one BSH file contains a whole day of time
  steps (96 per 24 h). The integration splits that into individual time steps, but
  note that a longer forecast horizon yields many frames (24 h = 96 frames). Only
  the BSH North Sea area is supported (which covers the NL/BE/FR coast); the finer
  sub-areas and the Baltic are not yet.
- **DMI** publishes one file per hour per run. For WAM that is 1–2 MB per hour;
  of DKSS (9 MB per hour, mostly currents at dozens of depths) the integration
  reads only the beginning with the surface fields, ~0.3 MB per hour. A new run
  appears every 6 hours, ~2.5 hours after its run time; a run is only picked up
  once every hour is online. Set the forecast horizon to what you need (e.g.
  120) — the default 24 hours uses only part of the 5 days.
- **Water level** in DMI DKSS is the height above that model's mean sea level,
  not above NAP (Dutch datum); don't compare it one-to-one with Dutch gauges.
- **Rijkswaterstaat** (NOOS-Matroos) interpolates every request to a regular grid
  on its own servers. To go easy on that service the integration takes one run
  every 6 hours (the models run every 3), in pieces of 7 hours. For DCSM that is
  ~2.5 MB per hour for the whole area (24 hours ahead: ~60 MB per run); SWAN
  North Sea ~1.6 MB and SWAN coast ~0.7 MB per hour. The models reach 48 hours.
  Matroos lists a run as soon as its first hours are out, so the integration asks
  with one small request whether the last hour is there yet; if it is not, the
  previous (finished) run stays until the new one is done — usually half an hour
  later.
- **DCSM water level**: interpolating to a regular grid leaves a handful of
  impossible values (8–12 m) along coasts and in enclosed basins. The
  integration removes cells that differ from their neighbours by more than 2 m
  (~0.04%); real extremes such as a spring tide at Saint-Malo stay. The water
  level is as the model delivers it, not converted to a local datum.
- **MET Norway** serves ready-made files per area (0.2–1.2 MB). Weather, waves
  and currents are each refreshed on their own schedule (weather about hourly);
  on every update the integration fetches the files for the chosen parameters
  again. Each content has its own run time and reach (see the table). The
  current is the one 3 m below the surface. The service requires apps to
  identify themselves; the integration sends its name and project address.
  Data: MET Norway, CC BY 4.0.

## Development & testing

```bash
python3 -m pip install -r requirements-dev.txt  # numpy, Pillow, paho-mqtt, homeassistant, pytest-homeassistant-custom-component
python3 -m pytest tests/
```

The following standalone dev scripts work without Home Assistant:

- `dev/verify_knmi_source.py` — checks the KNMI source implementation against the
  real Open Data API (dataset catalogue, file listing, download URL).
- `dev/render_preview.py <grib-file>` — decodes and renders all configured
  parameters from one GRIB lead-time file to PNGs in `dev/output/`, handy to
  visually check colormaps/reprojection.
- `dev/mock_server.py` + `dev/dev.html` — runs the map card in a real browser
  against a mocked API (reuses the PNGs from `dev/render_preview.py`), without
  needing a Home Assistant instance.
  `?lang=en` (or `?lang=nl`) mimics the Home Assistant user's language choice,
  so both languages can be checked.
- `dev/shots.html` — renders the four example cards from
  [Four example cards](#four-example-cards) one at a time at a fixed width, each
  on its own URL (`/shots.html?card=overlay`, `waves`, `compare`,
  `weathermap`), against that same mock server. The YAML lives in that page and
  a test keeps the README showing the same blocks.
- `python3 dev/toc.py` — rebuilds the two contents lists from the README's own
  headings. Run it when you add or rename a chapter; `tests/test_readme.py`
  fails otherwise.
- `dev/verify_knmi_mqtt.py <api-key>` — checks the connection to KNMI's MQTT
  Notification Service and shows incoming "new file" messages. Note: this needs a
  **self-registered** API key; the public anonymous demo key (which the REST API
  does accept) is rejected for MQTT.

`tests/test_coordinator.py`, `tests/test_http.py` and `tests/test_init.py` are
opt-in: set `GRIB_OVERLAY_SAMPLE_GRIB` to the path of a real decoded GRIB
lead-time file (see `dev/render_preview.py`'s docstring for how to get one) to run
them; otherwise they are skipped.

## Architecture / adding new sources

Each data source implements the `GribSource` interface in
`custom_components/grib_overlay/sources/base.py` (dataset catalogue, file listing,
download) and is registered in `sources/registry.py`. The rest of the integration
(coordinator, decode/render pipeline, HTTP API, map card) has no KNMI-specific
assumptions outside `sources/knmi.py` itself.

## License

[MIT](LICENSE)
