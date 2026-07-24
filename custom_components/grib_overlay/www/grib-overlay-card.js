/**
 * grib-overlay-card: Leaflet map showing a GRIB Weather Overlay dataset over
 * OpenSeaMap, with a single-time slider and a start/end/step animation mode.
 *
 * Plain vanilla custom element (no build step, no framework) so it can ship
 * as a single static file alongside the vendored Leaflet build.
 */

const LEAFLET_JS_URL = "/grib_overlay_static/vendor/leaflet/leaflet.js";
const LEAFLET_CSS_URL = "/grib_overlay_static/vendor/leaflet/leaflet.css";
const VELOCITY_JS_URL = "/grib_overlay_static/vendor/leaflet-velocity/leaflet-velocity.js";
const VELOCITY_CSS_URL = "/grib_overlay_static/vendor/leaflet-velocity/leaflet-velocity.css";

function loadScript(url, isReady) {
  if (isReady()) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = url;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Kon ${url} niet laden`));
    document.head.appendChild(script);
  });
}

let leafletLoadingPromise = null;
function loadLeaflet() {
  if (!leafletLoadingPromise) {
    leafletLoadingPromise = loadScript(LEAFLET_JS_URL, () => !!window.L).then(() => window.L);
  }
  return leafletLoadingPromise;
}

let velocityLoadingPromise = null;
function loadLeafletVelocity() {
  // leaflet-velocity extends L, so Leaflet must be loaded first.
  if (!velocityLoadingPromise) {
    velocityLoadingPromise = loadLeaflet().then(() =>
      loadScript(VELOCITY_JS_URL, () => !!(window.L && window.L.velocityLayer))
    );
  }
  return velocityLoadingPromise;
}

// Bilinearly sample a {nx,ny,lo1,la1,dx,dy} grid (north-first, row-major) at a
// lat/lon. Returns null outside the grid or where all corners are missing.
function sampleGrid(header, data, lat, lon) {
  const { nx, ny, lo1, la1, dx, dy } = header;
  if (nx < 2 || ny < 2 || !dx || !dy) return null;
  const fx = (lon - lo1) / dx;
  const fy = (la1 - lat) / dy; // la1 is north; rows increase southward
  if (fx < 0 || fy < 0 || fx > nx - 1 || fy > ny - 1) return null;
  const x0 = Math.floor(fx);
  const y0 = Math.floor(fy);
  const x1 = Math.min(x0 + 1, nx - 1);
  const y1 = Math.min(y0 + 1, ny - 1);
  const tx = fx - x0;
  const ty = fy - y0;
  const at = (x, y) => data[y * nx + x];
  const corners = [
    [at(x0, y0), (1 - tx) * (1 - ty)],
    [at(x1, y0), tx * (1 - ty)],
    [at(x0, y1), (1 - tx) * ty],
    [at(x1, y1), tx * ty],
  ];
  let sw = 0;
  let sv = 0;
  for (const [v, w] of corners) {
    if (v != null && isFinite(v)) {
      sw += w;
      sv += v * w;
    }
  }
  return sw === 0 ? null : sv / sw;
}

const COMPASS8 = ["N", "NO", "O", "ZO", "Z", "ZW", "W", "NW"];
function compass(deg) {
  return COMPASS8[Math.round(((deg % 360) / 45)) % 8];
}

function formatTime(isoString) {
  const date = new Date(isoString);
  return new Intl.DateTimeFormat("nl-NL", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

const STEP_OPTIONS = [
  { value: 1, label: "elke stap" },
  { value: 2, label: "om de 2 stappen" },
  { value: 3, label: "om de 3 stappen" },
  { value: 6, label: "om de 6 stappen" },
];

// Optional display-unit conversions applied client-side to the legend labels
// (the colour scale itself is a normalised ramp, so only the numbers/labels
// change). Keyed by the backend's source unit; factor multiplies the value.
const UNIT_CONVERSIONS = {
  "m/s": {
    kn: { factor: 1.9438445, label: "kn" }, // knots (nautical miles/hour)
    "km/h": { factor: 3.6, label: "km/u" },
    mph: { factor: 2.2369363, label: "mph" },
  },
  km: {
    NM: { factor: 0.5399568, label: "zeemijl" }, // nautical miles
  },
};

// Config values (any of these) that select the numeric 0-360 direction style;
// anything else falls back to the compass style.
const DIRECTION_DEG_ALIASES = new Set([
  "deg",
  "deg°",
  "degree",
  "degrees",
  "°",
  "graden",
  "360",
  "0-360",
  "0-360°",
]);

// Forgiving config aliases -> canonical target unit key above.
const UNIT_ALIASES = {
  kt: "kn",
  kts: "kn",
  knots: "kn",
  knopen: "kn",
  knoop: "kn",
  "km/u": "km/h",
  kmh: "km/h",
  kph: "km/h",
  nm: "NM",
  zeemijl: "NM",
  zeemijlen: "NM",
};

class GribOverlayCard extends HTMLElement {
  static getStubConfig() {
    return { type: "custom:grib-overlay-card" };
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
    this._applyLayout();
    // On a live config edit (e.g. changing wind_unit in the dashboard editor)
    // the card is already initialized; refresh the unit labels in place.
    if (this._entries) this._refreshUnitLabels();
  }

  // Re-label the parameter dropdown + legend for the current display units,
  // without rebuilding the dropdown or resetting the selected parameter.
  _refreshUnitLabels() {
    const entry = this._currentEntry();
    if (entry && this._els && this._els.paramSelect) {
      for (const opt of this._els.paramSelect.options) {
        const param = entry.parameters.find((p) => p.key === opt.value);
        if (param) opt.textContent = `${param.name} (${this._displayUnitLabel(param.unit)})`;
      }
    }
    this._updateLegend();
  }

  set hass(hass) {
    this._hass = hass;
    this._tryInitialize();
  }

  // Only build the Leaflet map once the card is both configured with hass AND
  // actually attached to the document -- creating Leaflet on a detached/zero-size
  // element is what left the map blank until a browser refresh.
  _tryInitialize() {
    if (this._initialized || !this._hass || !this.isConnected) return;
    this._initialized = true;
    this._initialize();
  }

  _rows() {
    const cfg = this._config || {};
    const rows = Number((cfg.grid_options && cfg.grid_options.rows) ?? cfg.rows);
    return rows > 0 ? rows : 8;
  }

  // Masonry dashboards use getCardSize (1 unit ~= 50px).
  getCardSize() {
    return this._rows();
  }

  // Sections dashboards size the card from getGridOptions() (the defaults) merged
  // with HA's own grid_options in the config (what the resize handles write, and
  // what always wins). We honour grid_options first, then the card's own
  // rows/columns keys, then sensible defaults -- and expose a wide min/max so
  // the card can always be dragged to any height.
  getGridOptions() {
    const cfg = this._config || {};
    const grid = cfg.grid_options || {};
    const columns =
      grid.columns !== undefined
        ? grid.columns
        : cfg.columns !== undefined
          ? cfg.columns
          : "full";
    const rows = grid.rows !== undefined ? grid.rows : this._rows();
    return {
      columns,
      rows,
      min_columns: 3,
      max_columns: 12,
      min_rows: 2,
      max_rows: 30,
    };
  }

  // Older HA builds called this getLayoutOptions; keep an alias so the card
  // sizes correctly on both.
  getLayoutOptions() {
    return this.getGridOptions();
  }

  // Set the map's preferred height (flex-basis) from the row count. In masonry
  // this is the actual map height; in a sections grid cell the map flexes from
  // this basis and may shrink (min-height:0) so the chrome never clips.
  _applyLayout() {
    if (!this._els || !this._els.mapContainer) return;
    const mapBasis = Math.max(160, Math.round(this._rows() * 64 - 150));
    this._els.mapContainer.style.height = `${mapBasis}px`;
    if (this._map) {
      requestAnimationFrame(() => this._map.invalidateSize());
    }
  }

  connectedCallback() {
    this._connected = true;
    // First attach: build the map now that we have a sized, in-DOM container.
    this._tryInitialize();
    // Re-attach (navigating back to the view): the container was hidden/removed,
    // so nudge Leaflet to re-measure and repaint its tiles + overlay.
    if (this._map) {
      this._observeResize();
      this._scheduleInvalidate();
    }
  }

  disconnectedCallback() {
    this._connected = false;
    this._stopPlayback();
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
      this._resizeObserver = null;
    }
  }

  _observeResize() {
    if (!window.ResizeObserver || !this._els || !this._els.mapContainer) return;
    if (this._resizeObserver) this._resizeObserver.disconnect();
    this._resizeObserver = new ResizeObserver(() => {
      if (this._map) this._map.invalidateSize();
    });
    this._resizeObserver.observe(this._els.mapContainer);
  }

  // Leaflet needs invalidateSize after its container gains size/visibility.
  // Fire it across a few frames/timeouts to catch late dashboard layout.
  _scheduleInvalidate() {
    if (!this._map) return;
    const nudge = () => this._map && this._map.invalidateSize();
    requestAnimationFrame(nudge);
    setTimeout(nudge, 150);
    setTimeout(nudge, 600);
  }

  // -- one-time DOM scaffold -------------------------------------------------

  _render() {
    if (this._built) return;
    this._built = true;

    const root = this.attachShadow({ mode: "open" });
    for (const href of [LEAFLET_CSS_URL, VELOCITY_CSS_URL]) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      root.appendChild(link);
    }

    const style = document.createElement("style");
    style.textContent = `
      :host { display: block; height: 100%; }
      ha-card {
        /* overflow-y auto is a safety net: if the card is made so short that
           even a zero-height map can't free enough room, the chrome scrolls
           instead of being clipped/falling off. */
        overflow-x: hidden; overflow-y: auto; height: 100%;
        display: flex; flex-direction: column;
      }
      .toolbar {
        display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
        padding: 6px 10px; flex: 0 0 auto;
      }
      .toolbar select { min-width: 0; }
      select, button {
        font: inherit; padding: 4px 8px; border-radius: 6px;
        border: 1px solid var(--divider-color, #ccc);
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color, #000);
      }
      button.active { background: var(--primary-color, #03a9f4); color: white; }
      /* The map is the only flexible row: its preferred height (the "rows"
         config, set inline) is the basis, min-height:0 lets it shrink in a
         short grid cell so the chrome below it never gets clipped/falls off. */
      .map-container { position: relative; width: 100%; flex: 1 1 auto; min-height: 0; }
      /* Absolute fill (not height:100%) so the map fills the container whether
         its height comes from a fixed grid cell (sections) or the inline basis
         (masonry) -- percentage heights don't resolve against an indefinite parent. */
      .map { position: absolute; inset: 0; }
      /* All chrome rows keep their natural height (never shrink) so they stay
         on the card when it's made short. */
      .toolbar, .time-controls, .legend, .note { flex: 0 0 auto; }
      .time-controls {
        display: flex; flex-wrap: wrap; gap: 8px 10px; align-items: center;
        padding: 8px 12px;
      }
      .progress-slider { flex: 1 1 100%; min-width: 120px; }
      .speed-control { display: flex; align-items: center; gap: 4px; flex: 0 0 auto; }
      .speed-control input[type="range"] { flex: 0 0 96px; width: 96px; }
      .time-label { flex: 1 1 auto; min-width: 130px; font-size: 0.9em; }
      .hidden { display: none !important; }
      .legend { padding: 4px 12px 12px; font-size: 0.8em; }
      .legend-bar { height: 10px; border-radius: 4px; margin: 4px 0 2px; }
      .legend-ticks { position: relative; height: 6px; }
      .legend-ticks span { position: absolute; top: 0; width: 1px; height: 4px;
        background: var(--secondary-text-color, #888); transform: translateX(-50%); }
      .legend-scale { display: flex; justify-content: space-between; }
      .legend-scale span { text-align: center; }
      .note { padding: 0 12px 8px; font-size: 0.8em; opacity: 0.7; }
      .readout {
        position: absolute; left: 8px; bottom: 8px; z-index: 500;
        background: rgba(255,255,255,0.85); color: #12324f;
        padding: 3px 8px; border-radius: 6px; font: 12px/1.3 sans-serif;
        pointer-events: none; box-shadow: 0 1px 3px rgba(0,0,0,0.3); max-width: 70%;
      }
    `;
    root.appendChild(style);

    const card = document.createElement("ha-card");
    card.innerHTML = `
      <div class="toolbar">
        <select class="entry-select"></select>
        <select class="param-select"></select>
        <button class="mode-single active" data-mode="single">Eén tijdstip</button>
        <button class="mode-animate" data-mode="animate">Animatie</button>
        <select class="render-mode-select" title="Weergave">
          <option value="raster">Raster</option>
          <option value="particles">Deeltjes (stroming)</option>
          <option value="vectors">Vectoren (pijlen)</option>
          <option value="wavevectors">Golfrichting (pijlen)</option>
        </select>
      </div>
      <div class="map-container"><div class="map"></div><div class="readout hidden"></div></div>
      <div class="time-controls single-controls">
        <input type="range" class="time-slider" min="0" max="0" value="0" step="1" />
        <span class="time-label"></span>
      </div>
      <div class="time-controls animate-controls hidden">
        <select class="start-select"></select>
        <span>t/m</span>
        <select class="end-select"></select>
        <select class="step-select"></select>
        <button class="play-pause">▶</button>
        <span class="speed-control" title="Afspeelsnelheid">🐢<input type="range" class="speed-slider" min="150" max="2000" value="1450" step="50" />🐇</span>
        <span class="time-label"></span>
        <input type="range" class="progress-slider" min="0" max="0" value="0" step="1" title="Positie in de animatie" />
      </div>
      <div class="legend">
        <div class="legend-bar"></div>
        <div class="legend-ticks"></div>
        <div class="legend-scale"></div>
      </div>
      <div class="note"></div>
    `;
    root.appendChild(card);

    this._els = {
      entrySelect: card.querySelector(".entry-select"),
      paramSelect: card.querySelector(".param-select"),
      modeSingleBtn: card.querySelector(".mode-single"),
      modeAnimateBtn: card.querySelector(".mode-animate"),
      renderModeSelect: card.querySelector(".render-mode-select"),
      mapContainer: card.querySelector(".map-container"),
      mapDiv: card.querySelector(".map"),
      readout: card.querySelector(".readout"),
      singleControls: card.querySelector(".single-controls"),
      animateControls: card.querySelector(".animate-controls"),
      timeSlider: card.querySelector(".single-controls .time-slider"),
      singleTimeLabel: card.querySelector(".single-controls .time-label"),
      startSelect: card.querySelector(".start-select"),
      endSelect: card.querySelector(".end-select"),
      stepSelect: card.querySelector(".step-select"),
      playPauseBtn: card.querySelector(".play-pause"),
      speedSlider: card.querySelector(".speed-slider"),
      progressSlider: card.querySelector(".progress-slider"),
      animateTimeLabel: card.querySelector(".animate-controls .time-label"),
      legendBar: card.querySelector(".legend-bar"),
      legendTicks: card.querySelector(".legend-ticks"),
      legendScale: card.querySelector(".legend-scale"),
      note: card.querySelector(".note"),
    };

    for (const opt of STEP_OPTIONS) {
      const el = document.createElement("option");
      el.value = String(opt.value);
      el.textContent = opt.label;
      this._els.stepSelect.appendChild(el);
    }

    this._els.entrySelect.addEventListener("change", () => this._onEntryChange());
    this._els.paramSelect.addEventListener("change", () => this._onParameterChange());
    this._els.modeSingleBtn.addEventListener("click", () => this._setMode("single"));
    this._els.modeAnimateBtn.addEventListener("click", () => this._setMode("animate"));
    this._els.timeSlider.addEventListener("input", () => this._showFrame(Number(this._els.timeSlider.value)));
    this._els.playPauseBtn.addEventListener("click", () => this._togglePlayback());
    this._els.startSelect.addEventListener("change", () => this._clampAnimationRange());
    this._els.endSelect.addEventListener("change", () => this._clampAnimationRange());
    // Scrubbing the animation progress bar pauses playback and jumps to that frame.
    this._els.progressSlider.addEventListener("input", () => {
      this._stopPlayback();
      this._showFrame(Number(this._els.progressSlider.value));
    });
    // Speed changes take effect immediately while playing.
    this._els.speedSlider.addEventListener("input", () => {
      if (this._playTimer) this._startPlaybackTimer();
    });
    this._els.renderModeSelect.addEventListener("change", () => this._onRenderModeChange());

    this._mode = "single";
    this._renderMode = this._config?.renderMode === "particles" ? "particles" : "raster";
    this._frames = [];
    this._boundsFit = false;
    this._windCache = new Map(); // wind_url -> fetched velocity data
    this._fieldCache = new Map(); // field_url -> fetched scalar grid
    this._paramFramesCache = new Map(); // param key -> frames (for wave arrows)
  }

  // -- data loading -----------------------------------------------------------

  async _initialize() {
    this._render();
    try {
      await loadLeaflet();
    } catch (err) {
      this._els.note.textContent = String(err.message || err);
      return;
    }
    this._map = window.L.map(this._els.mapDiv, {
      center: this._config.center || [52.1, 5.3],
      zoom: this._config.zoom || 7,
    });
    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(this._map);
    window.L.tileLayer("https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenSeaMap contributors",
      maxZoom: 18,
    }).addTo(this._map);

    // Hover shows the value at the cursor; tap/click pins it in a popup; hold /
    // right-click opens a meteogram at that point.
    this._map.on("mousemove", (e) => this._onMouseMove(e.latlng));
    this._map.on("mouseout", () => this._els.readout.classList.add("hidden"));
    this._map.on("click", (e) => this._onMapClick(e.latlng));
    this._map.on("contextmenu", (e) => {
      window.L.DomEvent.preventDefault(e.originalEvent);
      this._onMapHold(e.latlng);
    });
    // Wind-vector arrows are redrawn whenever the map moves/zooms/resizes.
    this._map.on("moveend zoomend resize", () => {
      if (this._renderMode === "vectors" || this._renderMode === "wavevectors") this._drawVectors();
    });

    // Observe resizes and force an initial re-measure, so tiles/overlay render
    // even when the card was first laid out at zero/unknown size.
    this._observeResize();
    this._applyLayout();
    this._scheduleInvalidate();

    await this._loadEntries();
  }

  async _loadEntries() {
    try {
      const data = await this._hass.callApi("GET", "grib_overlay/entries");
      this._entries = data.entries || [];
    } catch (err) {
      this._els.note.textContent = "Kon grib_overlay entries niet ophalen: " + (err.message || err);
      return;
    }

    if (!this._entries.length) {
      this._els.note.textContent =
        "Geen GRIB Weather Overlay integratie gevonden. Voeg de integratie eerst toe via Instellingen → Apparaten & diensten.";
      return;
    }

    this._els.entrySelect.innerHTML = "";
    for (const entry of this._entries) {
      const opt = document.createElement("option");
      opt.value = entry.entry_id;
      opt.textContent = entry.title;
      this._els.entrySelect.appendChild(opt);
    }
    this._els.entrySelect.value =
      this._resolveDefaultEntryId() || this._entries[0].entry_id;

    await this._onEntryChange();
  }

  // Which entry (dataset) to preselect when the card loads. `entry_id` (the exact
  // config-entry id) wins; otherwise `dataset` matches an entry by its dataset
  // key, its dataset name, or its title (as shown in the dropdown) -- all
  // case-insensitive. Returns null when nothing matches, so the caller falls
  // back to the first configured entry.
  _resolveDefaultEntryId() {
    const cfg = this._config || {};
    if (cfg.entry_id && this._entries.some((e) => e.entry_id === cfg.entry_id)) {
      return cfg.entry_id;
    }
    if (cfg.dataset) {
      const want = String(cfg.dataset).trim().toLowerCase();
      const match = this._entries.find(
        (e) =>
          (e.dataset.key || "").toLowerCase() === want ||
          (e.dataset.name || "").toLowerCase() === want ||
          (e.title || "").toLowerCase() === want,
      );
      if (match) return match.entry_id;
    }
    return null;
  }

  _currentEntry() {
    return this._entries.find((e) => e.entry_id === this._els.entrySelect.value);
  }

  // Resolve a source unit ("m/s"/"km") to the configured display conversion,
  // or null when no (valid) override applies and the source unit should stand.
  _conversionFor(sourceUnit) {
    const cfg = this._config || {};
    let target;
    if (sourceUnit === "m/s") target = cfg.wind_unit;
    else if (sourceUnit === "km") target = cfg.visibility_unit;
    if (!target) return null;
    target = UNIT_ALIASES[String(target).toLowerCase()] || target;
    if (target === sourceUnit) return null;
    return (UNIT_CONVERSIONS[sourceUnit] || {})[target] || null;
  }

  _displayUnitLabel(sourceUnit) {
    const conv = this._conversionFor(sourceUnit);
    return conv ? conv.label : sourceUnit;
  }

  // Wind-direction display style: "compass" (N/O/Z/W, default) or "deg" (0-360).
  _directionMode() {
    const raw = String((this._config && this._config.direction_unit) || "compass")
      .toLowerCase()
      .trim();
    return DIRECTION_DEG_ALIASES.has(raw) ? "deg" : "compass";
  }

  // Format a from-direction (degrees) per the configured style.
  _formatDirection(deg) {
    const d = ((deg % 360) + 360) % 360;
    return this._directionMode() === "deg" ? `${Math.round(d)}°` : compass(d);
  }

  async _onEntryChange() {
    const entry = this._currentEntry();
    if (!entry) return;

    this._els.paramSelect.innerHTML = "";
    for (const param of entry.parameters) {
      const opt = document.createElement("option");
      opt.value = param.key;
      opt.textContent = `${param.name} (${this._displayUnitLabel(param.unit)})`;
      this._els.paramSelect.appendChild(opt);
    }
    const wantedParam = this._config.parameter;
    this._els.paramSelect.value = entry.parameters.some((p) => p.key === wantedParam)
      ? wantedParam
      : entry.parameters[0]?.key || "";

    // Auto-fit to the dataset bounds only when the user hasn't pinned the view
    // via config; an explicit center/zoom must win over the auto-fit.
    const hasManualView = this._config.center !== undefined || this._config.zoom !== undefined;
    if (!this._boundsFit && !hasManualView) {
      const [south, west, north, east] = entry.dataset.bounds;
      this._map.fitBounds([[south, west], [north, east]]);
    }
    this._boundsFit = true;

    await this._onParameterChange();
  }

  async _onParameterChange() {
    const entry = this._currentEntry();
    const paramKey = this._els.paramSelect.value;
    if (!entry || !paramKey) return;

    this._stopPlayback();
    let data;
    try {
      data = await this._hass.callApi(
        "GET",
        `grib_overlay/frames/${entry.entry_id}?parameter=${encodeURIComponent(paramKey)}`
      );
    } catch (err) {
      this._els.note.textContent = "Kon frames niet ophalen: " + (err.message || err);
      return;
    }

    this._frames = (data[paramKey] || []).slice().sort((a, b) => a.valid_time.localeCompare(b.valid_time));
    this._els.note.textContent = this._frames.length
      ? ""
      : "Nog geen frames beschikbaar voor deze parameter (eerste download/verwerking loopt mogelijk nog).";

    const lastIndex = String(Math.max(0, this._frames.length - 1));
    this._els.timeSlider.max = lastIndex;
    this._els.timeSlider.value = "0";
    this._els.progressSlider.max = lastIndex;
    this._els.progressSlider.value = "0";
    this._removeWindLayer();
    this._removeVectors();
    this._closePointPopup();
    this._readoutSource = null;
    this._paramFramesCache.clear(); // frames may be a fresh run
    this._els.readout.classList.add("hidden");
    this._syncRenderModeAvailability();
    this._populateAnimationSelects();
    this._updateLegend();
    if (this._frames.length) {
      this._showFrame(0);
    }
  }

  _populateAnimationSelects() {
    const { startSelect, endSelect } = this._els;
    startSelect.innerHTML = "";
    endSelect.innerHTML = "";
    this._frames.forEach((frame, index) => {
      const label = formatTime(frame.valid_time);
      const startOpt = document.createElement("option");
      startOpt.value = String(index);
      startOpt.textContent = label;
      startSelect.appendChild(startOpt);

      const endOpt = document.createElement("option");
      endOpt.value = String(index);
      endOpt.textContent = label;
      endSelect.appendChild(endOpt);
    });
    startSelect.value = "0";
    endSelect.value = String(Math.max(0, this._frames.length - 1));
  }

  _clampAnimationRange() {
    const start = Number(this._els.startSelect.value);
    const end = Number(this._els.endSelect.value);
    if (end < start) {
      this._els.endSelect.value = String(start);
    }
  }

  // -- rendering ---------------------------------------------------------------

  _showFrame(index) {
    const frame = this._frames[index];
    if (!frame) return;
    this._frameIndex = index;
    const mode = this._activeMode(); // particles | vectors | wavevectors | null
    const [south, west, north, east] = frame.bounds;
    const bounds = [[south, west], [north, east]];

    // In an overlay mode the coloured raster stays as a dimmed background under
    // the particles/arrows (the windy.com look); otherwise it's the overlay.
    const opacity = mode ? 0.45 : 0.75;
    if (!this._imageOverlay) {
      this._imageOverlay = window.L.imageOverlay(frame.image_url, bounds, { opacity }).addTo(this._map);
    } else {
      this._imageOverlay.setUrl(frame.image_url);
      this._imageOverlay.setBounds(bounds);
      this._imageOverlay.setOpacity(opacity);
    }

    if (mode === "particles") {
      this._removeVectors();
      this._updateWindLayer(frame);
    } else if (mode === "vectors") {
      this._removeWindLayer();
      this._updateVectors(frame);
    } else if (mode === "wavevectors") {
      this._removeWindLayer();
      this._updateWaveVectors(frame);
    } else {
      this._removeWindLayer();
      this._removeVectors();
    }

    const label = `${formatTime(frame.valid_time)} (run ${formatTime(frame.run_time)})`;
    this._els.singleTimeLabel.textContent = label;
    this._els.animateTimeLabel.textContent = label;
    this._els.timeSlider.value = String(index);
    this._els.progressSlider.value = String(index); // keep the animation scrubber in sync
    this._currentLegend = frame.legend;
    this._updateLegend();
    this._loadReadoutSource(frame);

    // Prefetch the next frame's image so animation playback doesn't flicker.
    const next = this._frames[index + 1];
    if (next) {
      const img = new Image();
      img.src = next.image_url;
    }
  }

  // -- value readout at the cursor (all parameters) --------------------------

  // Load the grid the cursor readout samples for the current frame: wind params
  // use the u/v grid (speed + direction); scalar params use the field grid.
  async _loadReadoutSource(frame) {
    const token = (this._readoutToken = (this._readoutToken || 0) + 1);
    let source = null;
    try {
      if (frame.wind_url) {
        const d = await this._fetchWind(frame.wind_url);
        source = { kind: "wind", header: d[0].header, u: d[0].data, v: d[1].data };
      } else if (frame.field_url) {
        const d = await this._fetchJson(frame.field_url, this._fieldCache);
        source = { kind: "scalar", header: d, data: d.data, unit: frame.legend.unit };
      }
    } catch (err) {
      source = null;
    }
    if (token !== this._readoutToken) return; // a newer frame won the race
    this._readoutSource = source;
  }

  async _fetchJson(url, cache) {
    if (cache.has(url)) return cache.get(url);
    const data = await this._hass.callApi("GET", url.replace(/^\/api\//, ""));
    cache.set(url, data);
    return data;
  }

  // Value at a lat/lon for the current parameter, formatted in display units.
  // Returns null when there's no data there. For wind, also direction.
  _valueAt(latlng) {
    const src = this._readoutSource;
    if (!src) return null;
    if (src.kind === "wind") {
      const u = sampleGrid(src.header, src.u, latlng.lat, latlng.lng);
      const v = sampleGrid(src.header, src.v, latlng.lat, latlng.lng);
      if (u == null || v == null) return null;
      const speed = Math.hypot(u, v);
      const { text, unit } = this._displayValue(speed, "m/s");
      // Meteorological direction: where the wind comes FROM.
      const from = (270 - (Math.atan2(v, u) * 180) / Math.PI + 360) % 360;
      return { label: `${text} ${unit} · ${this._formatDirection(from)}` };
    }
    const value = sampleGrid(src.header, src.data, latlng.lat, latlng.lng);
    if (value == null) return null;
    const { text, unit } = this._displayValue(value, src.unit);
    return { label: `${text} ${unit}` };
  }

  _onMouseMove(latlng) {
    const r = this._valueAt(latlng);
    if (!r) {
      this._els.readout.classList.add("hidden");
      return;
    }
    this._els.readout.textContent = `${this._paramName()}: ${r.label}`;
    this._els.readout.classList.remove("hidden");
  }

  // -- wind overlays (particles / vectors) -----------------------------------

  // The active wind mode, or null when it doesn't apply (non-wind param or the
  // plain raster mode).
  _windMode() {
    if ((this._renderMode === "particles" || this._renderMode === "vectors") && this._paramHasWind()) {
      return this._renderMode;
    }
    return null;
  }

  _paramHasWind() {
    return this._frames.some((f) => f.wind_url);
  }

  // -- wave direction arrows --------------------------------------------------
  // Waves store direction (deg) and height (m) as separate scalar parameters,
  // so the arrows are synthesised from those two fields (unlike wind's u/v).

  _paramByUnit(unit) {
    const entry = this._currentEntry();
    return (entry && entry.parameters.find((p) => p.unit === unit)) || null;
  }

  _directionParam() {
    return this._paramByUnit("°");
  }

  _hasWaveVectors() {
    return !!this._directionParam();
  }

  // The active overlay mode, honouring what the current data supports.
  _activeMode() {
    if ((this._renderMode === "particles" || this._renderMode === "vectors") && this._paramHasWind()) {
      return this._renderMode;
    }
    if (this._renderMode === "wavevectors" && this._hasWaveVectors()) return "wavevectors";
    return null;
  }

  async _fetchParamFrames(paramKey) {
    if (this._paramFramesCache.has(paramKey)) return this._paramFramesCache.get(paramKey);
    const entry = this._currentEntry();
    const data = await this._hass.callApi(
      "GET",
      `grib_overlay/frames/${entry.entry_id}?parameter=${encodeURIComponent(paramKey)}`
    );
    const frames = (data[paramKey] || []).slice().sort((a, b) => a.valid_time.localeCompare(b.valid_time));
    this._paramFramesCache.set(paramKey, frames);
    return frames;
  }

  async _frameForParamAt(paramKey, validTime) {
    const frames = await this._fetchParamFrames(paramKey);
    return frames.find((f) => f.valid_time === validTime) || null;
  }

  async _updateWaveVectors(frame) {
    const dirParam = this._directionParam();
    if (!dirParam) {
      this._removeVectors();
      return;
    }
    const heightParam = this._paramByUnit("m");
    const token = (this._windToken = (this._windToken || 0) + 1);
    let dirField;
    let magField = null;
    try {
      const dirFrame = await this._frameForParamAt(dirParam.key, frame.valid_time);
      if (!dirFrame || !dirFrame.field_url) {
        this._removeVectors();
        return;
      }
      dirField = await this._fetchJson(dirFrame.field_url, this._fieldCache);
      if (heightParam) {
        const magFrame = await this._frameForParamAt(heightParam.key, frame.valid_time);
        if (magFrame && magFrame.field_url) {
          magField = await this._fetchJson(magFrame.field_url, this._fieldCache);
        }
      }
    } catch (err) {
      return;
    }
    if (token !== this._windToken || this._activeMode() !== "wavevectors") return;
    this._vectorData = this._buildWaveVectorData(dirField, magField);
    this._drawVectors();
  }

  // Turn a direction field (deg, "from") + optional height field (m) into the
  // same u/v structure the arrow drawer consumes. Arrow points the way the
  // waves travel (direction + 180), length scales with height (or uniform).
  _buildWaveVectorData(dirField, magField) {
    const n = dirField.data.length;
    const u = new Array(n).fill(0);
    const v = new Array(n).fill(0);
    const sameGrid =
      magField && magField.data && magField.data.length === n && magField.nx === dirField.nx;
    for (let i = 0; i < n; i++) {
      const dir = dirField.data[i];
      if (dir == null) continue;
      let mag = 1;
      if (sameGrid) {
        mag = magField.data[i];
        if (mag == null) continue;
      }
      const travel = ((dir + 180) * Math.PI) / 180; // meteorological "from" -> travel
      u[i] = mag * Math.sin(travel);
      v[i] = mag * Math.cos(travel);
    }
    const header = {
      nx: dirField.nx,
      ny: dirField.ny,
      lo1: dirField.lo1,
      la1: dirField.la1,
      dx: dirField.dx,
      dy: dirField.dy,
    };
    return [{ header, data: u }, { header, data: v }];
  }

  async _fetchWind(url) {
    if (this._windCache.has(url)) return this._windCache.get(url);
    // url is like "/api/grib_overlay/wind/..."; hass.callApi wants it without /api/.
    const data = await this._hass.callApi("GET", url.replace(/^\/api\//, ""));
    this._windCache.set(url, data);
    return data;
  }

  async _updateWindLayer(frame) {
    if (!frame.wind_url) {
      this._removeWindLayer();
      return;
    }
    const token = (this._windToken = (this._windToken || 0) + 1);
    let data;
    try {
      await loadLeafletVelocity();
      data = await this._fetchWind(frame.wind_url);
    } catch (err) {
      this._els.note.textContent = "Kon vectordata niet laden: " + (err.message || err);
      return;
    }
    if (token !== this._windToken || this._windMode() !== "particles") return;

    if (!this._windLayer) {
      this._windLayer = window.L.velocityLayer({
        displayValues: false, // our own cursor readout handles this, for all params
        data,
        maxVelocity: 30,
        velocityScale: 0.01,
      }).addTo(this._map);
    } else {
      this._windLayer.setData(data);
    }
  }

  _removeWindLayer() {
    if (this._windLayer) {
      this._map.removeLayer(this._windLayer);
      this._windLayer = null;
    }
  }

  // -- wind vectors (arrows) --------------------------------------------------

  async _updateVectors(frame) {
    if (!frame.wind_url) {
      this._removeVectors();
      return;
    }
    const token = (this._windToken = (this._windToken || 0) + 1);
    let data;
    try {
      data = await this._fetchWind(frame.wind_url);
    } catch (err) {
      this._els.note.textContent = "Kon vectordata niet laden: " + (err.message || err);
      return;
    }
    if (token !== this._windToken || this._windMode() !== "vectors") return;
    this._vectorData = data;
    this._drawVectors();
  }

  _ensureVectorSvg() {
    if (this._vectorSvg) return;
    const svgns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgns, "svg");
    svg.setAttribute("class", "wind-vectors");
    svg.style.cssText = "position:absolute;top:0;left:0;pointer-events:none;z-index:400;";
    const defs = document.createElementNS(svgns, "defs");
    defs.innerHTML =
      '<marker id="gribArrowHead" markerWidth="4" markerHeight="4" refX="3" refY="2" orient="auto">' +
      '<path d="M0,0 L4,2 L0,4 Z" fill="#12324f"/></marker>';
    svg.appendChild(defs);
    this._map.getContainer().appendChild(svg);
    this._vectorSvg = svg;
  }

  _drawVectors() {
    const m = this._activeMode();
    if (!this._vectorData || (m !== "vectors" && m !== "wavevectors")) return;
    this._ensureVectorSvg();
    const svg = this._vectorSvg;
    // Clear previous arrows (keep <defs>).
    [...svg.querySelectorAll("g")].forEach((g) => g.remove());
    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");

    const header = this._vectorData[0].header;
    const u = this._vectorData[0].data;
    const v = this._vectorData[1].data;
    const size = this._map.getSize();
    // Size the SVG to the whole map. Without explicit width/height an inline SVG
    // falls back to its 300x150 default and clips everything outside the top-left
    // corner (arrows only showed there); matching the map size makes 1 user unit
    // = 1 container pixel so the arrows land where we compute them.
    svg.setAttribute("width", size.x);
    svg.setAttribute("height", size.y);
    svg.setAttribute("viewBox", `0 0 ${size.x} ${size.y}`);
    svg.style.width = size.x + "px";
    svg.style.height = size.y + "px";
    const spacing = 44; // px between arrows on screen -> uniform coverage at any zoom
    const scale = 3.4; // px per m/s

    // Place arrows on a regular SCREEN grid and interpolate the wind there, so
    // the whole visible overlay is covered evenly regardless of zoom level.
    for (let py = spacing / 2; py < size.y; py += spacing) {
      for (let px = spacing / 2; px < size.x; px += spacing) {
        const ll = this._map.containerPointToLatLng([px, py]);
        const uu = sampleGrid(header, u, ll.lat, ll.lng);
        const vv = sampleGrid(header, v, ll.lat, ll.lng);
        if (uu == null || vv == null) continue;
        const speed = Math.hypot(uu, vv);
        if (speed < 0.3) continue;
        const len = Math.min(24, 5 + speed * scale);
        // East = +x, north = -y (screen y points down).
        const x2 = px + (uu / speed) * len;
        const y2 = py - (vv / speed) * len;
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("x1", px.toFixed(1));
        line.setAttribute("y1", py.toFixed(1));
        line.setAttribute("x2", x2.toFixed(1));
        line.setAttribute("y2", y2.toFixed(1));
        line.setAttribute("stroke", "#12324f");
        line.setAttribute("stroke-width", "1.6");
        line.setAttribute("marker-end", "url(#gribArrowHead)");
        line.setAttribute("opacity", "0.9");
        g.appendChild(line);
      }
    }
    svg.appendChild(g);
  }

  _removeVectors() {
    if (this._vectorSvg) {
      this._vectorSvg.remove();
      this._vectorSvg = null;
    }
    this._vectorData = null;
  }

  // -- point value (click) + meteogram (hold) --------------------------------

  async _fetchPointSeries(paramKey, latlng) {
    const entry = this._currentEntry();
    if (!entry) return null;
    const q = `lat=${latlng.lat.toFixed(4)}&lon=${latlng.lng.toFixed(4)}`;
    return this._hass.callApi(
      "GET",
      `grib_overlay/point/${entry.entry_id}/${encodeURIComponent(paramKey)}?${q}`
    );
  }

  _closePointPopup() {
    if (this._pointPopup && this._map) {
      this._map.closePopup(this._pointPopup);
      this._pointPopup = null;
    }
  }

  _paramName() {
    const entry = this._currentEntry();
    const key = this._els.paramSelect.value;
    const p = entry && entry.parameters.find((x) => x.key === key);
    return p ? p.name : key;
  }

  // Convert a stored value (source unit) to the configured display unit + label.
  _displayValue(value, sourceUnit) {
    const conv = this._conversionFor(sourceUnit);
    const factor = conv ? conv.factor : 1;
    const unit = conv ? conv.label : sourceUnit;
    return { text: value == null ? "–" : (value * factor).toFixed(1), unit };
  }

  // Tap/click pins the current value in a popup (works on touch, where there's
  // no hover). Uses the same client-side grid as the readout.
  _onMapClick(latlng) {
    const r = this._valueAt(latlng);
    if (!r) return;
    const frame = this._frames[this._frameIndex || 0];
    this._pointPopup = window.L.popup({ closeButton: true, autoPan: false })
      .setLatLng(latlng)
      .setContent(
        `<div style="font:13px sans-serif"><b>${this._paramName()}</b><br>${r.label}<br>` +
          `<span style="opacity:.7">${formatTime(frame.valid_time)}</span></div>`
      )
      .openOn(this._map);
  }

  async _onMapHold(latlng) {
    const paramKey = this._els.paramSelect.value;
    if (!paramKey || !this._frames.length) return;
    let resp;
    try {
      resp = await this._fetchPointSeries(paramKey, latlng);
    } catch (err) {
      return;
    }
    const series = (resp && resp.series) || [];
    if (!series.some((s) => s.value != null)) return;
    const hasDir = !!(resp && resp.direction_unit) && series.some((s) => s.direction != null);
    const svg = this._buildMeteogram(series, resp.unit, latlng, hasDir);
    this._pointPopup = window.L.popup({
      closeButton: true,
      autoPan: true,
      maxWidth: 340,
      className: "grib-meteogram-popup",
    })
      .setLatLng(latlng)
      .setContent(svg)
      .openOn(this._map);
  }

  _buildMeteogram(series, sourceUnit, latlng, hasDirection = false) {
    const conv = this._conversionFor(sourceUnit);
    const factor = conv ? conv.factor : 1;
    const unit = conv ? conv.label : sourceUnit;
    const pts = series
      .map((s) => ({
        t: new Date(s.valid_time).getTime(),
        v: s.value == null ? null : s.value * factor,
        dir: s.direction == null ? null : s.direction,
      }))
      .filter((p) => p.v != null);
    const showDir = hasDirection && pts.some((p) => p.dir != null);
    const dirMode = this._directionMode(); // "compass" | "deg"
    // Font sizes are in the SVG's own user units; the SVG then scales to fill the
    // popup width. Keep the viewBox modest and the fonts generous so the axis
    // labels stay readable on a phone instead of being scaled down to nothing.
    const W = 300;
    const H = 170;
    // Numeric 0-360 labels are wider ("360") than single compass letters.
    const rMargin = showDir ? (dirMode === "deg" ? 30 : 24) : 10;
    const m = { l: 42, r: rMargin, t: 14, b: 34 };
    const FS = 13; // axis label font-size, in user units
    const DIR_COLOR = "#e8833a";
    const px0 = m.l;
    const px1 = W - m.r;
    const py0 = m.t;
    const py1 = H - m.b;

    // "Nice numbers": round a range to a 1/2/5 x 10^k value so major gridlines
    // land on clean, human-readable numbers.
    const niceNum = (range, round) => {
      const exp = Math.floor(Math.log10(range));
      const f = range / Math.pow(10, exp);
      const nf = round
        ? f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10
        : f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
      return nf * Math.pow(10, exp);
    };

    // ---- y scale ----
    // A direction parameter (deg) always spans the full compass 0-360, so its
    // axis is fixed rather than scaled to the data range.
    const isDirection = sourceUnit === "°";
    let vmin, vmax, yStep, yMinorStep;
    if (isDirection) {
      vmin = 0;
      vmax = 360;
      yStep = 90;
      yMinorStep = 30;
    } else {
      const vals = pts.map((p) => p.v);
      let dmin = Math.min(...vals);
      let dmax = Math.max(...vals);
      if (dmax - dmin < 1e-6) {
        dmin -= 1;
        dmax += 1;
      }
      yStep = niceNum((dmax - dmin) / 4, true); // expand to nice, round bounds
      vmin = Math.floor(dmin / yStep) * yStep;
      vmax = Math.ceil(dmax / yStep) * yStep;
      const yMant = Math.round(yStep / Math.pow(10, Math.floor(Math.log10(yStep))));
      yMinorStep = yStep / (yMant === 2 ? 4 : 5); // keep minor steps round
    }

    // ---- x scale: clock-aligned hourly ticks; majors every N hours ----
    const t0 = pts[0].t;
    const t1 = pts[pts.length - 1].t;
    const spanH = (t1 - t0) / 3600000 || 1;
    const cand = [1, 2, 3, 6, 12, 24, 48];
    let xMajorH = cand[cand.length - 1];
    for (const c of cand) {
      if (spanH / c <= 6) {
        xMajorH = c;
        break;
      }
    }
    const hourTs = [];
    const d0 = new Date(t0);
    d0.setMinutes(0, 0, 0);
    if (d0.getTime() < t0) d0.setHours(d0.getHours() + 1);
    for (let tt = d0.getTime(); tt <= t1; tt += 3600000) hourTs.push(tt);

    const sx = (t) => px0 + ((t - t0) / (t1 - t0 || 1)) * (px1 - px0);
    const sy = (v) => py1 - ((v - vmin) / (vmax - vmin)) * (py1 - py0);

    const parts = [];
    // Major horizontal gridlines + y labels + major y tick marks.
    const nY = Math.round((vmax - vmin) / yStep);
    for (let i = 0; i <= nY; i++) {
      const v = vmin + i * yStep;
      const y = sy(v).toFixed(1);
      parts.push(`<line x1="${px0}" y1="${y}" x2="${px1}" y2="${y}" stroke="#d9dee3"/>`);
      parts.push(`<line x1="${px0 - 5}" y1="${y}" x2="${px0}" y2="${y}" stroke="#9aa5ad"/>`);
      parts.push(
        `<text x="${px0 - 8}" y="${(parseFloat(y) + FS / 3).toFixed(1)}" font-size="${FS}" fill="#666" text-anchor="end">${Number(v.toFixed(2))}</text>`
      );
    }
    // Minor y tick marks (skip positions that coincide with a major).
    const nYm = Math.round((vmax - vmin) / yMinorStep);
    for (let j = 0; j <= nYm; j++) {
      const v = vmin + j * yMinorStep;
      if (Math.abs(v / yStep - Math.round(v / yStep)) < 1e-6) continue; // on a major
      parts.push(`<line x1="${px0 - 3}" y1="${sy(v).toFixed(1)}" x2="${px0}" y2="${sy(v).toFixed(1)}" stroke="#c2c9cf"/>`);
    }
    // Major vertical gridlines + x labels + major x ticks; minor x ticks between.
    const pad2 = (n) => (n < 10 ? "0" + n : "" + n);
    const wd = new Intl.DateTimeFormat("nl-NL", { weekday: "short" });
    for (const tt of hourTs) {
      const hr = new Date(tt).getHours();
      const x = sx(tt).toFixed(1);
      if (hr % xMajorH === 0) {
        parts.push(`<line x1="${x}" y1="${py0}" x2="${x}" y2="${py1}" stroke="#d9dee3"/>`);
        parts.push(`<line x1="${x}" y1="${py1}" x2="${x}" y2="${(py1 + 5).toFixed(1)}" stroke="#9aa5ad"/>`);
        const label = hr === 0 ? wd.format(new Date(tt)) : pad2(hr);
        parts.push(
          `<text x="${x}" y="${H - 10}" font-size="${FS}" fill="#666" text-anchor="middle">${label}</text>`
        );
      } else {
        parts.push(`<line x1="${x}" y1="${py1}" x2="${x}" y2="${(py1 + 3).toFixed(1)}" stroke="#c2c9cf"/>`);
      }
    }
    // Axes (drawn over the gridlines).
    parts.push(`<line x1="${px0}" y1="${py1}" x2="${px1}" y2="${py1}" stroke="#aeb6bd"/>`);
    parts.push(`<line x1="${px0}" y1="${py0}" x2="${px0}" y2="${py1}" stroke="#aeb6bd"/>`);
    // ---- secondary axis: wind direction (0-360 deg, from-direction) ----
    if (showDir) {
      const sy2 = (d) => py1 - (d / 360) * (py1 - py0);
      const compassLbl = { 0: "N", 90: "O", 180: "Z", 270: "W", 360: "N" };
      // Major label per style: compass letters or the numeric bearing (0-360).
      const dirLabel = (d) => (dirMode === "deg" ? String(d) : compassLbl[d]);
      // Right axis line + 10-deg minor ticks (longer at 45s) + 90-deg majors.
      parts.push(`<line x1="${px1}" y1="${py0}" x2="${px1}" y2="${py1}" stroke="#e0a274"/>`);
      for (let d = 10; d < 360; d += 10) {
        if (d % 90 === 0) continue; // majors drawn below
        const y = sy2(d).toFixed(1);
        const medium = d % 30 === 0; // 30/60/120... slightly longer for orientation
        parts.push(
          `<line x1="${px1}" y1="${y}" x2="${(px1 + (medium ? 4 : 2.5)).toFixed(1)}" y2="${y}" stroke="#f0b487"/>`
        );
      }
      for (let d = 0; d <= 360; d += 90) {
        const y = sy2(d).toFixed(1);
        parts.push(`<line x1="${px1}" y1="${y}" x2="${(px1 + 5).toFixed(1)}" y2="${y}" stroke="${DIR_COLOR}"/>`);
        parts.push(
          `<text x="${(px1 + 8).toFixed(1)}" y="${(parseFloat(y) + FS / 3).toFixed(1)}" font-size="${FS}" fill="${DIR_COLOR}" text-anchor="start">${dirLabel(d)}</text>`
        );
      }
      // Direction line: break the path across the 0/360 wrap (jumps > 180 deg).
      let dpath = "";
      let prev = null;
      for (const p of pts) {
        if (p.dir == null) {
          prev = null;
          continue;
        }
        const cmd = prev == null || Math.abs(p.dir - prev) > 180 ? "M" : "L";
        dpath += `${cmd}${sx(p.t).toFixed(1)},${sy2(p.dir).toFixed(1)}`;
        prev = p.dir;
      }
      parts.push(
        `<path d="${dpath}" fill="none" stroke="${DIR_COLOR}" stroke-width="1.6" stroke-dasharray="4 3"/>`
      );
      parts.push(
        pts
          .filter((p) => p.dir != null)
          .map((p) => `<circle cx="${sx(p.t).toFixed(1)}" cy="${sy2(p.dir).toFixed(1)}" r="2" fill="${DIR_COLOR}"/>`)
          .join("")
      );
    }

    // Data line + dots (speed, on top, left axis).
    const line = pts.map((p, i) => `${i ? "L" : "M"}${sx(p.t).toFixed(1)},${sy(p.v).toFixed(1)}`).join(" ");
    parts.push(`<path d="${line}" fill="none" stroke="var(--primary-color,#03a9f4)" stroke-width="2.5"/>`);
    parts.push(
      pts
        .map((p) => `<circle cx="${sx(p.t).toFixed(1)}" cy="${sy(p.v).toFixed(1)}" r="2.2" fill="var(--primary-color,#03a9f4)"/>`)
        .join("")
    );

    // Primary series is wind speed or wave height, depending on the parameter.
    const primaryLabel = sourceUnit === "m" ? "hoogte" : "snelheid";
    const legend = showDir
      ? `<div style="font-size:11px;margin-top:1px">` +
        `<span style="color:var(--primary-color,#03a9f4)">━ ${primaryLabel} (${unit})</span>` +
        `&nbsp;&nbsp;<span style="color:${DIR_COLOR}">┅ richting (${dirMode === "deg" ? "°" : "kompas"})</span></div>`
      : "";
    return (
      `<div style="width:290px;max-width:78vw;font:14px sans-serif"><b>${this._paramName()}</b> · ${unit}` +
      `<div style="opacity:.6;font-size:12px">${latlng.lat.toFixed(2)}, ${latlng.lng.toFixed(2)}</div>` +
      legend +
      `<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block;margin-top:4px">` +
      parts.join("") +
      `</svg></div>`
    );
  }

  _onRenderModeChange() {
    const v = this._els.renderModeSelect.value;
    this._renderMode = ["particles", "vectors", "wavevectors"].includes(v) ? v : "raster";
    if (this._frames.length) this._showFrame(this._frameIndex || 0);
  }

  // Enable/disable overlay modes based on the available data: wind modes need a
  // wind (u/v) parameter, the wave-arrow mode needs a wave-direction parameter.
  _syncRenderModeAvailability() {
    const hasWind = this._paramHasWind();
    for (const value of ["particles", "vectors"]) {
      const opt = this._els.renderModeSelect.querySelector(`option[value="${value}"]`);
      if (opt) opt.disabled = !hasWind;
    }
    const hasWave = this._hasWaveVectors();
    const waveOpt = this._els.renderModeSelect.querySelector('option[value="wavevectors"]');
    if (waveOpt) waveOpt.disabled = !hasWave;

    if (!hasWind && (this._renderMode === "particles" || this._renderMode === "vectors")) {
      this._renderMode = "raster";
    }
    if (!hasWave && this._renderMode === "wavevectors") {
      this._renderMode = "raster";
    }
    this._els.renderModeSelect.value = this._renderMode;
  }

  _updateLegend() {
    const legend = this._currentLegend || this._frames[0]?.legend;
    if (!legend) {
      this._els.legendBar.style.background = "";
      this._els.legendTicks.innerHTML = "";
      this._els.legendScale.textContent = "";
      return;
    }
    const stops = legend.stops
      .map((s) => `${s.color} ${(s.offset * 100).toFixed(0)}%`)
      .join(", ");
    this._els.legendBar.style.background = `linear-gradient(to right, ${stops})`;

    const conv = this._conversionFor(legend.unit);
    const factor = conv ? conv.factor : 1;
    const unit = conv ? conv.label : legend.unit;

    // Intermediate ticks: five evenly spaced values across the range (not just
    // min/max), with tick marks aligned under the gradient bar.
    const TICKS = 5;
    const fmt = (v) => {
      const s = Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1);
      return s.replace(/\.0$/, "");
    };
    const scaleParts = [];
    const tickParts = [];
    for (let i = 0; i < TICKS; i++) {
      const t = i / (TICKS - 1);
      const value = (legend.min_value + (legend.max_value - legend.min_value) * t) * factor;
      const last = i === TICKS - 1;
      const text = last ? `${fmt(value)} ${unit}` : fmt(value);
      scaleParts.push(`<span>${text}</span>`);
      tickParts.push(`<span style="left:${(t * 100).toFixed(1)}%"></span>`);
    }
    this._els.legendTicks.innerHTML = tickParts.join("");
    this._els.legendScale.innerHTML = scaleParts.join("");
  }

  // -- mode + playback -----------------------------------------------------------

  _setMode(mode) {
    this._mode = mode;
    this._els.modeSingleBtn.classList.toggle("active", mode === "single");
    this._els.modeAnimateBtn.classList.toggle("active", mode === "animate");
    this._els.singleControls.classList.toggle("hidden", mode !== "single");
    this._els.animateControls.classList.toggle("hidden", mode !== "animate");
    if (mode !== "animate") this._stopPlayback();
  }

  _togglePlayback() {
    if (this._playTimer) {
      this._stopPlayback();
    } else {
      this._startPlayback();
    }
  }

  // Slider value runs slow->fast left->right; convert to a frame interval (ms).
  _playInterval() {
    const s = this._els.speedSlider;
    const min = Number(s.min);
    const max = Number(s.max);
    return min + max - Number(s.value);
  }

  _startPlayback() {
    if (!this._frames.length) return;
    this._playStart = Number(this._els.startSelect.value);
    this._playEnd = Number(this._els.endSelect.value);
    this._playStep = Number(this._els.stepSelect.value) || 1;
    this._playIndex = this._playStart;
    this._showFrame(this._playIndex);
    this._els.playPauseBtn.textContent = "⏸";
    this._startPlaybackTimer();
  }

  _startPlaybackTimer() {
    if (this._playTimer) clearInterval(this._playTimer);
    this._playTimer = setInterval(() => {
      this._playIndex += this._playStep;
      if (this._playIndex > this._playEnd) this._playIndex = this._playStart;
      this._showFrame(this._playIndex);
    }, this._playInterval());
  }

  _stopPlayback() {
    if (this._playTimer) {
      clearInterval(this._playTimer);
      this._playTimer = null;
    }
    if (this._els?.playPauseBtn) this._els.playPauseBtn.textContent = "▶";
  }
}

customElements.define("grib-overlay-card", GribOverlayCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "grib-overlay-card",
  name: "GRIB Weather Overlay",
  description: "GRIB-weerdata als kaartlaag over OpenSeaMap, met tijd-slider en animatie.",
});
