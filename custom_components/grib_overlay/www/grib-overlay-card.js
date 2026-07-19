/**
 * grib-overlay-card: Leaflet map showing a GRIB Weather Overlay dataset over
 * OpenSeaMap, with a single-time slider and a start/end/step animation mode.
 *
 * Plain vanilla custom element (no build step, no framework) so it can ship
 * as a single static file alongside the vendored Leaflet build.
 */

const LEAFLET_JS_URL = "/grib_overlay_static/vendor/leaflet/leaflet.js";
const LEAFLET_CSS_URL = "/grib_overlay_static/vendor/leaflet/leaflet.css";

let leafletLoadingPromise = null;
function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (!leafletLoadingPromise) {
    leafletLoadingPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = LEAFLET_JS_URL;
      script.onload = () => resolve(window.L);
      script.onerror = () => reject(new Error("Kon Leaflet niet laden"));
      document.head.appendChild(script);
    });
  }
  return leafletLoadingPromise;
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

class GribOverlayCard extends HTMLElement {
  static getStubConfig() {
    return { type: "custom:grib-overlay-card" };
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
    this._applyLayout();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._initialize();
    }
  }

  _rows() {
    const rows = Number(this._config && this._config.rows);
    return rows > 0 ? rows : 8;
  }

  // Masonry dashboards use getCardSize (1 unit ~= 50px).
  getCardSize() {
    return this._rows();
  }

  // Sections dashboards use getGridOptions: columns/rows control width/height,
  // and can also be dragged in the UI. Default to full width. `columns` may be
  // a number (grid columns to span) or "full"; `rows` is height in grid rows.
  getGridOptions() {
    const cfg = this._config || {};
    const columns = cfg.columns === undefined ? "full" : cfg.columns;
    return {
      columns,
      rows: this._rows(),
      min_columns: 3,
      min_rows: 3,
    };
  }

  // Older HA builds called this getLayoutOptions; keep an alias so the card
  // sizes correctly on both.
  getLayoutOptions() {
    return this.getGridOptions();
  }

  // Give the map a sensible floor height derived from the row count so it looks
  // right in masonry dashboards; in sections it flexes to fill the grid cell.
  _applyLayout() {
    if (!this._els || !this._els.mapContainer) return;
    const mapMin = Math.max(160, Math.round(this._rows() * 64 - 150));
    this._els.mapContainer.style.minHeight = `${mapMin}px`;
    if (this._map) {
      requestAnimationFrame(() => this._map.invalidateSize());
    }
  }

  connectedCallback() {
    this._connected = true;
  }

  disconnectedCallback() {
    this._connected = false;
    this._stopPlayback();
    if (this._resizeObserver) {
      this._resizeObserver.disconnect();
      this._resizeObserver = null;
    }
  }

  // -- one-time DOM scaffold -------------------------------------------------

  _render() {
    if (this._built) return;
    this._built = true;

    const root = this.attachShadow({ mode: "open" });
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = LEAFLET_CSS_URL;
    root.appendChild(link);

    const style = document.createElement("style");
    style.textContent = `
      :host { display: block; height: 100%; }
      ha-card {
        overflow: hidden; height: 100%;
        display: flex; flex-direction: column;
      }
      .toolbar {
        display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
        padding: 8px 12px; flex: 0 0 auto;
      }
      select, button {
        font: inherit; padding: 4px 8px; border-radius: 6px;
        border: 1px solid var(--divider-color, #ccc);
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color, #000);
      }
      button.active { background: var(--primary-color, #03a9f4); color: white; }
      /* map-container flexes to fill the height the dashboard gives the card;
         min-height (set from the "rows" config) is the floor used in masonry
         dashboards where no fixed card height is imposed. */
      .map-container { position: relative; width: 100%; flex: 1 1 auto; min-height: 240px; }
      /* Absolute fill (not height:100%) so the map fills the container whether
         its height comes from a fixed grid cell (sections) or from flex/min-height
         (masonry) -- percentage heights don't resolve against an indefinite parent. */
      .map { position: absolute; inset: 0; }
      .time-controls {
        display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
        padding: 8px 12px;
      }
      .time-controls input[type="range"] { flex: 1; min-width: 120px; }
      .time-label { min-width: 130px; font-size: 0.9em; }
      .hidden { display: none !important; }
      .legend { padding: 4px 12px 12px; font-size: 0.8em; }
      .legend-bar {
        height: 10px; border-radius: 4px; margin: 4px 0;
      }
      .legend-scale { display: flex; justify-content: space-between; }
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
        <select class="render-mode-select">
          <option value="raster">Raster</option>
          <option value="particles" disabled>Windpijltjes (binnenkort)</option>
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
        <input type="range" class="speed-slider" min="150" max="2000" value="700" step="50" title="Snelheid" />
        <span class="time-label"></span>
      </div>
      <div class="legend"><div class="legend-bar"></div><div class="legend-scale"></div></div>
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
      animateTimeLabel: card.querySelector(".animate-controls .time-label"),
      legendBar: card.querySelector(".legend-bar"),
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

    this._mode = "single";
    this._frames = [];
    this._boundsFit = false;
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
    this._map = window.L.map(this._els.mapDiv, { center: this._config.center || [52.1, 5.3], zoom: this._config.zoom || 7 });
    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(this._map);
    window.L.tileLayer("https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenSeaMap contributors",
      maxZoom: 18,
    }).addTo(this._map);

    // Leaflet needs an explicit nudge whenever its container is resized (grid
    // resize, section relayout, window resize), otherwise tiles/overlay clip.
    if (window.ResizeObserver && this._els.mapContainer) {
      this._resizeObserver = new ResizeObserver(() => {
        if (this._map) this._map.invalidateSize();
      });
      this._resizeObserver.observe(this._els.mapContainer);
    }
    this._applyLayout();

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

  async _onEntryChange() {
    const entry = this._currentEntry();
    if (!entry) return;

    this._els.paramSelect.innerHTML = "";
    for (const param of entry.parameters) {
      const opt = document.createElement("option");
      opt.value = param.key;
      opt.textContent = `${param.name} (${param.unit})`;
      this._els.paramSelect.appendChild(opt);
    }
    const wantedParam = this._config.parameter;
    this._els.paramSelect.value = entry.parameters.some((p) => p.key === wantedParam)
      ? wantedParam
      : entry.parameters[0]?.key || "";

    if (!this._boundsFit) {
      const [south, west, north, east] = entry.dataset.bounds;
      this._map.fitBounds([[south, west], [north, east]]);
      this._boundsFit = true;
    }

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

    this._els.timeSlider.max = String(Math.max(0, this._frames.length - 1));
    this._els.timeSlider.value = "0";
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
    const [south, west, north, east] = frame.bounds;
    const bounds = [[south, west], [north, east]];

    if (!this._imageOverlay) {
      this._imageOverlay = window.L.imageOverlay(frame.image_url, bounds, { opacity: 0.75 }).addTo(this._map);
    } else {
      this._imageOverlay.setUrl(frame.image_url);
      this._imageOverlay.setBounds(bounds);
    }

    const label = `${formatTime(frame.valid_time)} (run ${formatTime(frame.run_time)})`;
    this._els.singleTimeLabel.textContent = label;
    this._els.animateTimeLabel.textContent = label;
    this._els.timeSlider.value = String(index);
    this._currentLegend = frame.legend;
    this._updateLegend();

    // Prefetch the next frame's image so animation playback doesn't flicker.
    const next = this._frames[index + 1];
    if (next) {
      const img = new Image();
      img.src = next.image_url;
    }
  }

  _updateLegend() {
    const legend = this._currentLegend || this._frames[0]?.legend;
    if (!legend) {
      this._els.legendBar.style.background = "";
      this._els.legendScale.textContent = "";
      return;
    }
    const stops = legend.stops
      .map((s) => `${s.color} ${(s.offset * 100).toFixed(0)}%`)
      .join(", ");
    this._els.legendBar.style.background = `linear-gradient(to right, ${stops})`;
    this._els.legendScale.innerHTML = `<span>${legend.min_value.toFixed(1)} ${legend.unit}</span><span>${legend.max_value.toFixed(1)} ${legend.unit}</span>`;
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

  _startPlayback() {
    if (!this._frames.length) return;
    const start = Number(this._els.startSelect.value);
    const end = Number(this._els.endSelect.value);
    const step = Number(this._els.stepSelect.value) || 1;
    let index = start;
    this._showFrame(index);
    this._els.playPauseBtn.textContent = "⏸";
    this._playTimer = setInterval(() => {
      index += step;
      if (index > end) index = start;
      this._showFrame(index);
    }, Number(this._els.speedSlider.value));
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
