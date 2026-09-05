# GRIB Weather Overlay voor Home Assistant

> **Taal / Language:** 🇳🇱 Nederlands (hieronder) · 🇬🇧 [English documentation](#english) (onderaan deze pagina)

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
# measurement_radius_km: 10   # meteogram → vergelijk modellen → Meting: straal voor nabije meetstations
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
WaterWebservices (`OphalenCatalogus` → dichtstbijzijnde station → `OphalenWaarnemingen`,
AQUO-parametermodel). De exacte codes/aanroepen kunnen per provider afwijken; bij een
mislukking zie je nu een melding in de card **én** een `WARNING` in de HA-log met de
exacte oorzaak. De response-parsers zijn met fixtures getest. *(Neerslag komt van KNMI
als intensiteit `rg` in mm/u — geen directe som per interval; hou daar rekening mee.)*

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
| `observations_api_key` | tekst | (leeg) | KNMI Open Data-sleutel mét toegang tot `10-minute-in-situ-meteorological-observations`, voor het **downloaden van stationswaarnemingen**. Je HARMONIE-sleutel heeft daar vaak géén toegang toe (KNMI geeft 403). Leeg = HARMONIE-sleutel hergebruiken |
| `alias` | tekst | (leeg) | **korte naam** voor deze bron, getoond als compact label in de vergelijking en het meteogram (bv. `KNMI NL`). Leeg = automatisch afgeleid uit de bron (bronnen van dezelfde soort worden vanzelf onderscheiden) |
| `storage_path` | tekst | (leeg) | **map voor de werkbestanden** (run-archief, gedecodeerde leden, gerenderde cache). Leeg = `/share/grib_overlay` op HAOS/Supervised, anders de tijdelijke systeemmap. Zet dit **nooit** binnen `/config`: die map gaat in elke back-up (zie [Back-ups](#back-ups)) |
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

Home Assistant zet de **hele** `/config`-map in elke back-up. Tot en met v0.25
stonden de werkbestanden van deze integratie daar ook, met twee gevolgen: de
back-up werd honderden MB's groter dan nodig, en als een bestand precies tussen
"back-up inventariseert" en "back-up schrijft" verdween, faalde de **héle**
back-up met `FileNotFoundError`.

**Sinds v0.26 schrijft de integratie niets meer in `/config`.** Alles — het
run-archief, de uitgepakte GRIB-leden en de gerenderde PNG/JSON-cache — staat
buiten de configuratiemap:

| Installatie | Standaardlocatie |
| --- | --- |
| Home Assistant OS / Supervised | `/share/grib_overlay/…` |
| Core / Container (of geen `/share`) | tijdelijke systeemmap (`/tmp/grib_overlay/…`) |

`/share` is de standaard omdat het echte schijf is en buiten de config-tar valt;
`/tmp` is binnen HAOS namelijk een *tmpfs* (RAM) en dus geen plek voor een
archief van ~850MB. Met de optie **Map voor werkbestanden** kies je desgewenst
zelf een pad. Zet dat nooit binnen `/config`.

Extra's:

- **Automatische opruiming bij het updaten.** De oude cache in
  `/config/grib_overlay/…` wordt bij de eerste start na de update verplaatst of
  (als dat een filesystem-grens kruist, wat op HAOS het geval is) weggegooid —
  het is een cache, die binnen enkele minuten opnieuw is opgebouwd. Zie het
  `WARNING` in het logboek. Zo wordt je back-up direct kleiner.
- **Ruwe downloads apart.** Het archief en de uitgepakte leden leven in een
  aparte scratch-map naast de run-mappen, zodat het opruimen van oude runs nooit
  een lopende download kan raken.
- **Pauze tijdens de back-up.** Via HA's back-up-platform (`async_pre_backup` /
  `async_post_backup`) pauzeert de integratie het verwerken en opruimen van runs
  zolang een back-up loopt. Dit is nu een tweede vangnet (voor het opruimen
  hierboven, en voor wie de map bewust tóch in `/config` zet): het was
  onvoldoende als vaste oplossing, omdat het verwerken van een run langer kan
  duren dan de wachttijd waarna de back-up alsnog begint.

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
  Met `?lang=en` (of `?lang=nl`) bootst de harness de taalkeuze van de
  HA-gebruiker na, zodat je beide talen kunt controleren.
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
- [DWD Open Data](https://opendata.dwd.de/) — the **EWAM wave model** for the
  European seas (significant wave height, mean wave direction and period), GRIB2,
  **no key**.
- [BSH](https://www.bsh.de/) — **sea current** (surface u/v) for the whole North
  Sea including the Dutch, Belgian and northern French coast, 15-minute steps,
  GRIB1, **no key** (open FTP).

## Features

- Configurable parameters: wind (10m), gusts, temperature (2m), dew point (2m),
  relative humidity (2m), precipitation, mean-sea-level pressure, visibility,
  cloud cover.
- **Waves** (DWD EWAM): significant wave height, mean wave direction and wave
  period as a colour layer over the European seas — with a meteogram and a
  value-under-the-cursor, just like the other parameters.
- **Sea current** (BSH): surface current (speed + direction) for the North Sea
  as a colour layer with particles/arrows — like wind, but for the water. At
  15-minute resolution, so fine tidal detail.
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
  reliable fallback if the MQTT connection fails for any reason. Your regular
  Open Data API key works for this; a separate Notification Service key is not
  required.

## Requirements

- Home Assistant OS or Supervised. All dependencies are pure-Python / universal
  wheels (`numpy`, `Pillow`, `paho-mqtt`); both GRIB1 (KNMI) and GRIB2 (DWD EWAM,
  simple packing) are read by a bundled custom decoder, so **no** `eccodes`/`cfgrib`
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
2. Choose the source. For **KNMI Data Platform** enter your Open Data API key (it
   is also used for the push notifications/MQTT; the optional **Notification
   Service API key** field can be left empty). For **DWD Open Data (waves)** leave
   the key fields empty — DWD needs no key.
3. Choose a dataset. KNMI: HARMONIE-AROME Cy43 **Netherlands** (default) or
   **Europe (DINI)**. DWD: **EWAM** (European waves). If you want both weather and
   waves, add two integration instances (one per source); in the card you switch
   between instances.
4. Choose which parameters should be kept up to date.
5. Optional: via the integration options, adjust the forecast horizon (default
   24 hours, max 60 hours — that is as far as the KNMI HARMONIE forecast reaches),
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

The integration provides **two** Lovelace cards:

- **`custom:grib-overlay-card`** — the map with the GRIB overlay, time
  slider/animation and the detailed meteogram (all parameters of every source at
  a point).
- **`custom:grib-overlay-compare-card`** — a **model comparison**: pick one
  parameter and see, at a point (click on the mini-map), what the different GRIB
  sources predict, as a **line chart + table** per model. The same comparison is
  also in the detailed meteogram under **Weergave → “vergelijk modellen”** (View →
  compare models).

### Overlay card (`grib-overlay-card`)

Add a card of type `custom:grib-overlay-card`, for example via a dashboard's YAML
editor:

```yaml
type: custom:grib-overlay-card
# optional: fix a specific dataset/parameter on load
# dataset: bsh_current_northsea   # dataset key, name, or the title from the picker
# entry_id: <config entry id>     # exact config entry (wins over dataset)
# parameter: wind_10m
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

### Model-comparison card (`grib-overlay-compare-card`)

Compare, at one point, what the different sources predict. Click on the mini-map
to move the point; at the top choose the parameter and the column time step.

```yaml
type: custom:grib-overlay-compare-card
parameter: wind_10m          # initial parameter (union of all sources)
center: [52.98, 4.12]        # initial position of the mini-map (e.g. a harbour)
zoom: 9
# meteogram_resolution: 3uur # table column time step: kwartier, uur, 3uur or dag
# entries: [knmi, dwd]       # optional: compare only these sources
#                            #   (match on source, dataset key/name, title or entry-id)
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
(`OphalenCatalogus` → nearest station → `OphalenWaarnemingen`, AQUO parameter model). The
exact codes/requests may differ per provider; on a failure you now get a message in the
card **and** a `WARNING` in the HA log with the exact cause. The response parsers are
covered by fixture tests. *(Precipitation comes from KNMI as intensity `rg` in mm/h — not
a direct per-interval sum; keep that in mind.)*

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
  lines) and/or `particle_base_opacity` (dim the raster further).
- `vectors` — arrows (direction + magnitude), coloured by wind speed with an
  outline; **wind only**.
- `wavevectors` — arrows for the wave direction; **waves only**.

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

## All settings — reference

Complete, exact list of every key and value you can use in the integration
(config-flow/options) and in the card YAML. The keys are case-sensitive; use them
exactly as below.

### Sources (`source`)

| `source` | Name | API key |
| --- | --- | --- |
| `knmi` | KNMI Data Platform | yes (Open Data key) |
| `dwd` | DWD Open Data (waves) | no |
| `bsh` | BSH (North Sea current) | no |

### Datasets (`dataset`)

| Source | `dataset` | Name | Grid | Horizon (max) | Step |
| --- | --- | --- | --- | --- | --- |
| `knmi` | `harmonie_arome_cy43_p1` | HARMONIE-AROME Cy43 — Netherlands | regular lat/lon | 60 h | 1 h |
| `knmi` | `harmonie_arome_cy43_p3` | HARMONIE-AROME Cy43 — Europe (DINI) | rotated lat/lon | 60 h | 1 h |
| `dwd` | `ewam` | DWD EWAM — European waves | regular lat/lon | 78 h | 1 h |
| `bsh` | `bsh_current_northsea` | BSH — North Sea current | regular lat/lon | 48 h | 15 min |

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

**DWD** (`ewam`):

| `parameter` | Name | Unit | Type |
| --- | --- | --- | --- |
| `wave_height` | Wave height (significant) | m | scalar |
| `wave_period` | Wave period (mean) | s | scalar |
| `wave_direction` | Wave direction (mean) | ° | scalar |

**BSH** (`bsh_current_northsea`):

| `parameter` | Name | Unit | Type |
| --- | --- | --- | --- |
| `current` | Sea current (surface) | m/s | vector |

The **type** determines which views are available: `vector` parameters
(`wind_10m`, `wind_gust_10m`, `current`) support `particles`/`vectors`; a direction
parameter (unit °, i.e. `wave_direction`) enables `wavevectors`; and `pressure_msl`
(unit hPa) enables the isobar layer.

### Integration: setup fields (config flow)

| Key | Values |
| --- | --- |
| `source` | `knmi`, `dwd` or `bsh` |
| `api_key` | KNMI Open Data key (leave empty for DWD/BSH) |
| `notification_api_key` | optional; KNMI push key (empty = polling only) |
| `dataset` | a dataset key from the table above |
| `parameters` | list of parameter keys you want to keep up to date |

### Integration: options (Configure)

| Key | Type | Default | Range / form |
| --- | --- | --- | --- |
| `forecast_horizon_hours` | number (hours) | `24` | 1–60 |
| `retain_runs` | integer | `2` | 1–10 |
| `update_interval_minutes` | integer (min) | `30` | 5–180 |
| `notification_api_key` | text | (empty) | KNMI push key |
| `observations_api_key` | text | (empty) | KNMI Open Data key with access to `10-minute-in-situ-meteorological-observations`, for **downloading station observations**. Your HARMONIE key is often not authorised for it (KNMI returns 403). Empty = reuse the HARMONIE key |
| `alias` | text | (empty) | **short name** for this source, shown as the compact label in the comparison and meteogram (e.g. `KNMI NL`). Empty = derived automatically from the source (same-source entries are disambiguated automatically) |
| `storage_path` | text | (empty) | **folder for the working files** (run archive, decoded members, rendered cache). Empty = `/share/grib_overlay` on HAOS/Supervised, otherwise the system temp folder. **Never** point this inside `/config`: that folder goes into every backup (see [Backups](#backups)) |
| `color_scales` | multi-line text | (empty) | per line: `parameter: value:#hex, value:#hex, …` (values in the parameter's **own unit**) |

### Card settings (Lovelace YAML)

| Key | Type | Default | Values / meaning |
| --- | --- | --- | --- |
| `dataset` | text | (first) | dataset key, name or title — which dataset on load |
| `entry_id` | text | (first) | exact config entry id (wins over `dataset`) |
| `parameter` | text | (first) | parameter key — which parameter on load |
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
| `columns` | `full` or number | `full` | width in a Sections dashboard |
| `rows` | number | — | height in grid rows (masonry) / initial size |
| `grid_options` | object | — | HA-native `{rows, columns}` (wins over `rows`/`columns`) |
| `wind_unit` | text | `m/s` | `m/s`, `kn`, `km/h`, `mph` |
| `visibility_unit` | text | `km` | `km`, `NM` |
| `direction_unit` | text | `compass` | `compass`, `deg` |
| `meteogram_parameters` | list or text | — | parameter keys that are **visible by default** in the detailed meteogram; the rest starts hidden (enable via the chips). Empty = show all rows. Match on parameter key, so it applies to all sources |
| `meteogram_resolution` | text | `uur` | time step of the meteogram columns: `kwartier`, `uur`, `3uur` or `dag`. For `dag` the daily average (precipitation: daily sum); finer = value at that time. Also switchable via “Kolommen” in the window itself |

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
| `entries` (or `models`) | list or text | — | compare only these sources; match on `source`, dataset key/name, title or entry-id. Empty = all sources that have the parameter |
| `meteogram_resolution` | text | `uur` | column time step of the table: `kwartier`, `uur`, `3uur`, `dag` |
| `wind_unit`, `visibility_unit`, `direction_unit` | text | see below | same unit options as the overlay card |

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

Home Assistant puts the **entire** `/config` folder into every backup. Up to
v0.25 this integration's working files lived there too, with two consequences:
backups grew hundreds of MB larger than necessary, and if a file disappeared
right between "backup takes inventory" and "backup writes", the **whole** backup
failed with `FileNotFoundError`.

**Since v0.26 the integration writes nothing inside `/config`.** Everything — the
run archive, the extracted GRIB members and the rendered PNG/JSON cache — lives
outside the config folder:

| Installation | Default location |
| --- | --- |
| Home Assistant OS / Supervised | `/share/grib_overlay/…` |
| Core / Container (or no `/share`) | system temp folder (`/tmp/grib_overlay/…`) |

`/share` is the default because it is real disk and outside the config tar; on
HAOS `/tmp` is a *tmpfs* (RAM), which is no place for a ~850MB archive. The
**Working files folder** option lets you pick your own path. Never point it
inside `/config`.

Also:

- **Automatic cleanup on upgrade.** The old cache in `/config/grib_overlay/…` is
  moved on the first start after the update, or dropped when that would cross a
  filesystem boundary (it does on HAOS) — it is a cache and is rebuilt within
  minutes. Look for the `WARNING` in the log. Your backup shrinks straight away.
- **Raw downloads kept apart.** The archive and the extracted members live in a
  scratch directory *beside* the run directories, so cleaning up old runs can
  never touch an in-flight download.
- **Pause during the backup.** Via HA's backup platform (`async_pre_backup` /
  `async_post_backup`) the integration pauses processing and cleaning up runs
  while a backup runs. This is now a second line of defence (for the cleanup
  above, and for anyone who deliberately points the folder back into `/config`):
  it was not enough on its own, because decoding a run can outlast the drain
  timeout after which the backup proceeds anyway.

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
- From **DWD Open Data** only the **EWAM wave model** is supported (for now). EWAM
  uses simple GRIB2 packing and is therefore readable without a binary library;
  other DWD models (e.g. ICON-EU) often use CCSDS/AEC or JPEG2000 compression,
  which would require such a library.
- **BSH sea current** is 15-minute data: one BSH file contains a whole day of time
  steps (96 per 24 h). The integration splits that into individual time steps, but
  note that a longer forecast horizon yields many frames (24 h = 96 frames). Only
  the BSH North Sea area is supported (which covers the NL/BE/FR coast); the finer
  sub-areas and the Baltic are not yet.

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
