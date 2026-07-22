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
          <option value="particles">Wind (deeltjes)</option>
        </select>
      </div>
      <div class="map-container"><div class="map"></div></div>
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
    const wanted = this._config.entry_id;
    this._els.entrySelect.value = this._entries.some((e) => e.entry_id === wanted)
      ? wanted
      : this._entries[0].entry_id;

    await this._onEntryChange();
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
    const particles = this._particlesActive();
    const [south, west, north, east] = frame.bounds;
    const bounds = [[south, west], [north, east]];

    // In particle mode the coloured raster stays as a dimmed background under
    // the animated particles (the windy.com look); otherwise it's the overlay.
    const opacity = particles ? 0.45 : 0.75;
    if (!this._imageOverlay) {
      this._imageOverlay = window.L.imageOverlay(frame.image_url, bounds, { opacity }).addTo(this._map);
    } else {
      this._imageOverlay.setUrl(frame.image_url);
      this._imageOverlay.setBounds(bounds);
      this._imageOverlay.setOpacity(opacity);
    }

    if (particles) {
      this._updateWindLayer(frame);
    } else {
      this._removeWindLayer();
    }

    const label = `${formatTime(frame.valid_time)} (run ${formatTime(frame.run_time)})`;
    this._els.singleTimeLabel.textContent = label;
    this._els.animateTimeLabel.textContent = label;
    this._els.timeSlider.value = String(index);
    this._els.progressSlider.value = String(index); // keep the animation scrubber in sync
    this._currentLegend = frame.legend;
    this._updateLegend();

    // Prefetch the next frame's image so animation playback doesn't flicker.
    const next = this._frames[index + 1];
    if (next) {
      const img = new Image();
      img.src = next.image_url;
    }
  }

  // -- wind particle layer (leaflet-velocity) --------------------------------

  // Particles apply only when the user chose particle mode AND the current
  // parameter actually has wind (u/v) data available.
  _particlesActive() {
    return this._renderMode === "particles" && this._paramHasWind();
  }

  _paramHasWind() {
    return this._frames.some((f) => f.wind_url);
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
      this._els.note.textContent = "Kon winddata niet laden: " + (err.message || err);
      return;
    }
    // A newer frame was requested while we were fetching -> drop this result.
    if (token !== this._windToken || !this._particlesActive()) return;

    if (!this._windLayer) {
      this._windLayer = window.L.velocityLayer({
        displayValues: true,
        displayOptions: {
          velocityType: "Wind",
          position: "bottomleft",
          emptyString: "geen winddata",
          angleConvention: "bearingCW",
          speedUnit: "m/s",
        },
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

  _onRenderModeChange() {
    this._renderMode = this._els.renderModeSelect.value === "particles" ? "particles" : "raster";
    if (this._frames.length) this._showFrame(this._frameIndex || 0);
  }

  // Enable/disable the particle option based on whether the current parameter
  // has wind data; fall back to raster when it doesn't.
  _syncRenderModeAvailability() {
    const hasWind = this._paramHasWind();
    const opt = this._els.renderModeSelect.querySelector('option[value="particles"]');
    if (opt) opt.disabled = !hasWind;
    if (!hasWind && this._renderMode === "particles") {
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
