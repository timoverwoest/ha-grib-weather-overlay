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

// Base overlay render modes selectable in the card / settable via `render_mode`
// config. Isobars are NOT a base mode -- they are a separate layer (a toggle)
// that draws on top of whichever base mode is active.
const RENDER_MODES = ["raster", "particles", "vectors", "wavevectors"];

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

// Parse a "#rrggbb" (or "#rgb") legend colour into an [r, g, b] triplet.
function hexToRgb(hex) {
  let h = String(hex || "").trim().replace(/^#/, "");
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  const n = parseInt(h, 16);
  return Number.isFinite(n) ? [(n >> 16) & 255, (n >> 8) & 255, n & 255] : [128, 128, 128];
}

// Separable Gaussian smoothing of a north-first scalar grid (the field_grid
// dict), with `sigmaKm` the smoothing scale in kilometres. Null cells are
// skipped and weights renormalised so gaps don't bleed. Used to bring the MSL
// pressure field to a synoptic scale before drawing isobars and finding H/L
// centres, so both are consistent and free of mesoscale noise.
function smoothField(field, sigmaKm) {
  const { nx, ny, lo1, la1, dx, dy, data } = field;
  if (!(sigmaKm > 0) || nx < 3 || ny < 3) return field;
  const KM_PER_DEG = 111.32;
  const midLat = la1 - ((ny - 1) * dy) / 2;
  const sy = sigmaKm / (dy * KM_PER_DEG);
  const sx = sigmaKm / (dx * KM_PER_DEG * Math.max(0.1, Math.cos((midLat * Math.PI) / 180)));
  const kernel = (s) => {
    const rad = Math.max(1, Math.min(40, Math.ceil(s * 3)));
    const w = [];
    let sum = 0;
    for (let i = -rad; i <= rad; i++) {
      const v = Math.exp(-(i * i) / (2 * s * s));
      w.push(v);
      sum += v;
    }
    return { rad, w: w.map((v) => v / sum) };
  };
  const kx = kernel(sx);
  const ky = kernel(sy);
  const src = data.map((v) => (v == null || !isFinite(v) ? NaN : v));
  const tmp = new Float64Array(nx * ny);
  for (let y = 0; y < ny; y++) {
    for (let x = 0; x < nx; x++) {
      let acc = 0;
      let wsum = 0;
      for (let i = -kx.rad; i <= kx.rad; i++) {
        const xx = x + i;
        if (xx < 0 || xx >= nx) continue;
        const v = src[y * nx + xx];
        if (Number.isNaN(v)) continue;
        const w = kx.w[i + kx.rad];
        acc += v * w;
        wsum += w;
      }
      tmp[y * nx + x] = wsum > 0 ? acc / wsum : NaN;
    }
  }
  const out = new Array(nx * ny);
  for (let y = 0; y < ny; y++) {
    for (let x = 0; x < nx; x++) {
      let acc = 0;
      let wsum = 0;
      for (let j = -ky.rad; j <= ky.rad; j++) {
        const yy = y + j;
        if (yy < 0 || yy >= ny) continue;
        const v = tmp[yy * nx + x];
        if (Number.isNaN(v)) continue;
        const w = ky.w[j + ky.rad];
        acc += v * w;
        wsum += w;
      }
      out[y * nx + x] = wsum > 0 ? acc / wsum : null;
    }
  }
  return { nx, ny, lo1, la1, dx, dy, data: out };
}

// Marching squares over a north-first scalar grid (the field_grid dict). Returns
// contour segments [[lat1,lon1,lat2,lon2], ...] where the field crosses `level`.
// Used to draw isobars from the MSL-pressure field.
function marchingSquares(field, level) {
  const { nx, ny, lo1, la1, dx, dy, data } = field;
  const segs = [];
  const at = (x, y) => data[y * nx + x];
  const lon = (x) => lo1 + x * dx;
  const lat = (y) => la1 - y * dy; // row 0 = north
  // Position where the edge from corner a (value va) to corner b (value vb)
  // crosses `level`, linearly interpolated, as [lat, lon].
  const cross = (xa, ya, va, xb, yb, vb) => {
    const t = vb === va ? 0.5 : (level - va) / (vb - va);
    return [lat(ya + (yb - ya) * t), lon(xa + (xb - xa) * t)];
  };
  for (let y = 0; y < ny - 1; y++) {
    for (let x = 0; x < nx - 1; x++) {
      const tl = at(x, y);
      const tr = at(x + 1, y);
      const br = at(x + 1, y + 1);
      const bl = at(x, y + 1);
      if (tl == null || tr == null || br == null || bl == null) continue;
      let idx = 0;
      if (tl >= level) idx |= 8;
      if (tr >= level) idx |= 4;
      if (br >= level) idx |= 2;
      if (bl >= level) idx |= 1;
      if (idx === 0 || idx === 15) continue;
      const top = () => cross(x, y, tl, x + 1, y, tr);
      const right = () => cross(x + 1, y, tr, x + 1, y + 1, br);
      const bottom = () => cross(x, y + 1, bl, x + 1, y + 1, br);
      const left = () => cross(x, y, tl, x, y + 1, bl);
      const push = (a, b) => segs.push([a[0], a[1], b[0], b[1]]);
      switch (idx) {
        case 1: case 14: push(left(), bottom()); break;
        case 2: case 13: push(bottom(), right()); break;
        case 3: case 12: push(left(), right()); break;
        case 4: case 11: push(top(), right()); break;
        case 6: case 9: push(top(), bottom()); break;
        case 7: case 8: push(left(), top()); break;
        case 5: push(left(), top()); push(bottom(), right()); break;
        case 10: push(top(), right()); push(left(), bottom()); break;
      }
    }
  }
  return segs;
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
    this._closeDetailMeteogram();
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
      /* Detailed meteogram: a modal overlay with a Windy-style table (one row per
         parameter, colour-coded value cells, all sharing one time-column header). */
      .grib-detail-backdrop {
        position: fixed; inset: 0; z-index: 1200;
        background: rgba(0,0,0,0.45);
        display: flex; align-items: center; justify-content: center; padding: 10px;
      }
      .grib-detail-modal {
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color, #12324f);
        border-radius: 12px; box-shadow: 0 10px 44px rgba(0,0,0,0.45);
        max-width: min(1120px, 97vw); max-height: 94vh;
        display: flex; flex-direction: column; overflow: hidden;
      }
      .grib-detail-head {
        display: flex; align-items: baseline; gap: 10px; flex: 0 0 auto;
        padding: 10px 14px; border-bottom: 1px solid var(--divider-color, #e2e2e2);
      }
      .grib-detail-title { font: 600 15px/1.2 sans-serif; }
      .grib-detail-sub { font: 12px/1.2 sans-serif; opacity: 0.6; }
      .grib-detail-close {
        margin-left: auto; border: none; background: transparent; color: inherit;
        font-size: 20px; line-height: 1; cursor: pointer; padding: 2px 8px; border-radius: 6px;
      }
      .grib-detail-close:hover { background: var(--divider-color, #eee); }
      .grib-detail-tools {
        display: flex; align-items: center; gap: 8px; flex-wrap: wrap; flex: 0 0 auto;
        padding: 6px 12px; border-bottom: 1px solid var(--divider-color, #e2e2e2);
        font: 12px/1.4 sans-serif;
      }
      .grib-detail-tools .hint { opacity: 0.6; }
      .grib-detail-tools .chips { display: flex; gap: 6px; flex-wrap: wrap; }
      .grib-detail-tools .chip, .grib-detail-tools .showall {
        font: inherit; cursor: pointer; color: inherit;
        border: 1px solid var(--divider-color, #c7ccd1);
        background: var(--card-background-color, #fff);
        border-radius: 999px; padding: 1px 9px;
      }
      .grib-detail-tools .showall { border-radius: 6px; margin-left: auto; }
      .grib-detail-tools .chip:hover, .grib-detail-tools .showall:hover {
        border-color: var(--primary-color, #0288d1); color: var(--primary-color, #0288d1);
      }
      .grib-detail-scroll { overflow: auto; flex: 1 1 auto; }
      .grib-detail-loading {
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        gap: 12px; padding: 44px 30px; min-height: 120px; opacity: 0.85; font: 13px sans-serif;
      }
      .grib-spinner {
        width: 30px; height: 30px; border-radius: 50%;
        border: 3px solid var(--divider-color, #d9dee3);
        border-top-color: var(--primary-color, #03a9f4);
        animation: grib-spin 0.8s linear infinite;
      }
      @keyframes grib-spin { to { transform: rotate(360deg); } }
      .grib-detail-table { border-collapse: collapse; font: 12px/1.1 sans-serif; }
      .grib-detail-table th, .grib-detail-table td { text-align: center; white-space: nowrap; }
      .grib-detail-table .cell { width: 34px; min-width: 34px; height: 24px;
        font-variant-numeric: tabular-nums; }
      .grib-detail-table .rowlabel {
        position: sticky; left: 0; z-index: 2; text-align: right;
        background: var(--card-background-color, #fff);
        padding: 2px 10px 2px 12px; min-width: 92px; font-weight: 600;
        box-shadow: 1px 0 0 var(--divider-color, #e2e2e2);
      }
      .grib-detail-table .rowlabel .ru { display: block; font-weight: 400; opacity: 0.6; font-size: 11px; }
      .grib-detail-table thead th { position: sticky; top: 0; z-index: 3;
        background: var(--card-background-color, #fff); }
      .grib-detail-table thead th.rowlabel { z-index: 4; }
      .grib-detail-table .dayhead { padding: 3px 6px; font-weight: 600;
        border-bottom: 1px solid var(--divider-color, #e2e2e2); }
      .grib-detail-table .daysep { box-shadow: inset 2px 0 0 var(--divider-color, #c7ccd1); }
      .grib-detail-table .nowcol { box-shadow: inset 1px 0 0 var(--primary-color, #03a9f4),
        inset -1px 0 0 var(--primary-color, #03a9f4); }
      .grib-detail-table thead .nowcol { color: var(--primary-color, #03a9f4); font-weight: 700; }
      .grib-detail-table .windrow .cell { color: var(--primary-text-color, #33506b); }
      .grib-detail-table .arrowcell { padding: 2px 0; line-height: 1; }
      .grib-detail-table .arrowcell .arw { display: block; font-size: 14px; line-height: 1; }
      .grib-detail-table .arrowcell .dirnum { display: block; font-size: 10px; line-height: 1.2; opacity: 0.7; }
      .grib-detail-table .valrow td.cell { border-top: 1px solid rgba(255,255,255,0.35); }
      .grib-detail-table td.rowlabel[data-grp] { cursor: pointer; }
      .grib-detail-table td.rowlabel[data-grp]:hover { color: var(--primary-color, #0288d1); }
      .grib-detail-note {
        position: sticky; left: 0; padding: 8px 12px; font: 12px/1.4 sans-serif; opacity: 0.7;
        border-top: 1px solid var(--divider-color, #e2e2e2);
      }
      .grib-detail-table .grouprow td {
        background: var(--secondary-background-color, #eef1f4);
        border-top: 1px solid var(--divider-color, #e2e2e2);
      }
      .grib-detail-table .grouphead { text-align: left; padding: 5px 12px; font: 600 12px/1.2 sans-serif; }
      .grib-detail-table .grouplabel { text-align: left; padding: 5px 10px; }
      .grib-detail-table .grouplabel .src {
        display: inline-block; padding: 0 5px;
        font-size: 11px; font-weight: 700; letter-spacing: 0.02em; opacity: 0.85;
        border: 1px solid var(--divider-color, #c7ccd1); border-radius: 4px;
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
        <label class="isobars-toggle-label" title="Isobaren + hoge-/lagedrukcentra bovenop de overlay">
          <input type="checkbox" class="isobars-toggle" /> Isobaren
        </label>
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
      isobarsToggle: card.querySelector(".isobars-toggle"),
      isobarsToggleLabel: card.querySelector(".isobars-toggle-label"),
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
    this._els.isobarsToggle.addEventListener("change", () => this._onIsobarsToggle());

    this._mode = "single";
    // Default base overlay mode: honour a configured `render_mode` (or the legacy
    // `renderMode`) when it names a real mode; otherwise plain raster. The
    // availability check downgrades to raster if the mode doesn't fit the data.
    const wantedMode = this._config?.render_mode ?? this._config?.renderMode;
    this._renderMode = RENDER_MODES.includes(wantedMode) ? wantedMode : "raster";
    // Isobars + pressure centres are a separate overlay layer (default off).
    this._isobarsOn = !!this._config?.show_isobars;
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
    // Our arrows/isobars live in this pane so they sit above the raster
    // (overlayPane, z-index 400) but below Leaflet's popups (popupPane, 700) --
    // otherwise the click/meteogram popups render behind them. It is inside the
    // (transformed) map pane, so the overlays are drawn in layer coordinates.
    this._map.createPane("gribOverlay");
    const overlayPane = this._map.getPane("gribOverlay");
    overlayPane.style.zIndex = "450";
    overlayPane.style.pointerEvents = "none"; // clicks fall through to the map
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
    // Screen-space overlays (arrows, isobars) are redrawn on every map move.
    // Nothing to redraw until entries + frames have loaded (early invalidateSize
    // events fire before then), so bail out to avoid touching unset state.
    this._map.on("moveend zoomend resize", () => {
      if (!this._entries || !this._frames || !this._frames.length) return;
      const m = this._activeMode();
      if (m === "vectors" || m === "wavevectors") this._drawVectors();
      if (this._isobarsOn && this._pressureParam()) this._drawIsobars();
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
    // Guard against early calls (e.g. a map resize event) before entries load.
    return (this._entries || []).find((e) => e.entry_id === this._els.entrySelect.value);
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
    // Particles dim the raster more so they stay visible against it (a common
    // mobile problem); `particle_base_opacity` overrides that dimming.
    let opacity = 0.75;
    if (mode === "particles") {
      const d = Number(this._config && this._config.particle_base_opacity);
      opacity = d >= 0 && d <= 1 ? d : 0.35;
    } else if (mode) {
      opacity = 0.45;
    }
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

    // Isobars + pressure centres are an independent layer on top of the base
    // overlay above, drawn from the entry's pressure parameter for this time.
    if (this._isobarsOn && this._pressureParam()) this._updateIsobarOverlay(frame);
    else this._removeIsobars();

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

  // The entry's mean-sea-level pressure parameter (unit hPa), or null. Isobars +
  // pressure centres are drawn from it, independent of the selected parameter, so
  // they can overlay any other overlay of the same dataset.
  _pressureParam() {
    const entry = this._currentEntry();
    return (entry && entry.parameters.find((p) => p.unit === "hPa")) || null;
  }

  // The active base overlay mode, honouring what the current data supports.
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
      this._windLayer = window.L.velocityLayer(this._velocityOptions(data)).addTo(this._map);
    } else {
      this._windLayer.setData(data);
    }
  }

  // Particle options, with contrast-oriented defaults (thicker lines than the
  // library default of 1) and card overrides: `particle_width` (line width) and
  // `particle_color` (a single #hex makes the particles that one colour instead
  // of the velocity-coloured default -- often easier to see, e.g. on mobile).
  _velocityOptions(data) {
    const cfg = this._config || {};
    const opts = {
      displayValues: false, // our own cursor readout handles this, for all params
      data,
      maxVelocity: 30,
      velocityScale: 0.01,
      lineWidth: Number(cfg.particle_width) > 0 ? Number(cfg.particle_width) : 2,
    };
    const pc = String(cfg.particle_color || "").trim();
    if (/^#?[0-9a-f]{6}$/i.test(pc)) {
      const hex = pc.startsWith("#") ? pc : "#" + pc;
      opts.colorScale = [hex, hex]; // uniform colour across the whole speed range
    }
    return opts;
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
    // In the gribOverlay pane (z-index handled there); positioned per redraw.
    svg.style.cssText = "position:absolute;pointer-events:none;";
    const defs = document.createElementNS(svgns, "defs");
    // Three arrowheads: a fixed dark one (wave arrows), a white one (the casing
    // under coloured wind arrows) and one that inherits the line colour via
    // context-stroke (the coloured head itself). Heads scale with stroke width,
    // so the thicker white casing line yields a slightly larger head that reads
    // as an outline around the coloured head on top.
    // The coloured wind head and its white casing use userSpaceOnUse units so
    // their size is fixed (not multiplied by the thick casing stroke width) --
    // the casing head is only ~1px larger all round, so the halo hugs the head
    // tightly instead of ballooning. The dark head (wave arrows) is unchanged.
    defs.innerHTML =
      '<marker id="gribArrowHead" markerWidth="4" markerHeight="4" refX="3" refY="2" orient="auto">' +
      '<path d="M0,0 L4,2 L0,4 Z" fill="#12324f"/></marker>' +
      '<marker id="gribArrowHeadCasing" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" refX="8.4" refY="4.3" orient="auto">' +
      '<path d="M0,0 L8.4,4.3 L0,8.6 Z" fill="context-stroke"/></marker>' +
      '<marker id="gribArrowHeadColor" markerUnits="userSpaceOnUse" markerWidth="7.4" markerHeight="7.4" refX="7" refY="3.5" orient="auto">' +
      '<path d="M0,0 L7,3.5 L0,7 Z" fill="context-stroke"/></marker>';
    svg.appendChild(defs);
    this._map.getPane("gribOverlay").appendChild(svg);
    this._vectorSvg = svg;
  }

  // Build a value -> CSS colour function from a legend's colour stops, so the
  // wind arrows can be tinted by speed with exactly the raster's colours.
  _colorFromLegend(legend) {
    if (!legend || !legend.stops || legend.stops.length === 0) return null;
    const { min_value: lo, max_value: hi, stops } = legend;
    const span = hi - lo || 1;
    const hex = (c) => {
      const m = /^#?([0-9a-f]{6})$/i.exec(c);
      if (!m) return [0, 0, 0];
      const n = parseInt(m[1], 16);
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    };
    const rgb = stops.map((s) => ({ off: s.offset, c: hex(s.color) }));
    return (value) => {
      const t = Math.max(0, Math.min(1, (value - lo) / span));
      let a = rgb[0];
      let b = rgb[rgb.length - 1];
      for (let i = 0; i < rgb.length - 1; i++) {
        if (t >= rgb[i].off && t <= rgb[i + 1].off) {
          a = rgb[i];
          b = rgb[i + 1];
          break;
        }
      }
      const f = b.off === a.off ? 0 : (t - a.off) / (b.off - a.off);
      const mix = (i) => Math.round(a.c[i] + (b.c[i] - a.c[i]) * f);
      return `rgb(${mix(0)},${mix(1)},${mix(2)})`;
    };
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
    this._positionOverlaySvg(svg, size);
    const spacing = 44; // px between arrows on screen -> uniform coverage at any zoom
    const scale = 3.4; // px per m/s
    // Wind arrows are tinted by speed (with the raster's own colours) over a
    // casing so they keep contrast against the dimmed overlay. The casing colour
    // (halo) is configurable via `arrow_halo_color` (default white). Wave arrows
    // stay a single dark colour (their "speed" isn't wind speed).
    const colorFn = m === "vectors" ? this._colorFromLegend(this._currentLegend) : null;
    const haloColor = this._config?.arrow_halo_color || "#ffffff";
    const svgns = "http://www.w3.org/2000/svg";
    const addLine = (px, py, x2, y2, stroke, width, marker, opacity) => {
      const line = document.createElementNS(svgns, "line");
      line.setAttribute("x1", px.toFixed(1));
      line.setAttribute("y1", py.toFixed(1));
      line.setAttribute("x2", x2.toFixed(1));
      line.setAttribute("y2", y2.toFixed(1));
      line.setAttribute("stroke", stroke);
      line.setAttribute("stroke-width", width);
      line.setAttribute("stroke-linecap", "round");
      line.setAttribute("marker-end", marker);
      line.setAttribute("opacity", opacity);
      g.appendChild(line);
    };

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
        if (colorFn) {
          addLine(px, py, x2, y2, haloColor, "3.6", "url(#gribArrowHeadCasing)", "0.85");
          addLine(px, py, x2, y2, colorFn(speed), "1.7", "url(#gribArrowHeadColor)", "1");
        } else {
          addLine(px, py, x2, y2, "#12324f", "1.6", "url(#gribArrowHead)", "0.9");
        }
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

  // -- isobars + pressure centres (a layer on top of the base overlay) -------
  // Drawn from the dataset's pressure parameter for the current valid time, so
  // they can sit over any other overlay (wind, temperature, ...) of that dataset.

  async _updateIsobarOverlay(frame) {
    const pParam = this._pressureParam();
    if (!pParam) {
      this._removeIsobars();
      return;
    }
    const token = (this._isobarToken = (this._isobarToken || 0) + 1);
    let field = null;
    try {
      // Find the pressure frame at the same valid time as the shown frame.
      let pf = frame;
      if (pParam.key !== this._els.paramSelect.value) {
        const pframes = await this._fetchParamFrames(pParam.key);
        pf = pframes.find((f) => f.valid_time === frame.valid_time) || null;
      }
      if (pf && pf.field_url) field = await this._fetchJson(pf.field_url, this._fieldCache);
    } catch (err) {
      field = null;
    }
    if (token !== this._isobarToken || !this._isobarsOn) return;
    this._isobarField = field;
    if (field) this._drawIsobars();
    else this._removeIsobars();
  }

  _ensureIsobarSvg() {
    if (this._isobarSvg) return;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "isobar-overlay");
    // In the gribOverlay pane; appended after the wind arrows so the isobars +
    // H/L labels read on top of them. Positioned per redraw.
    svg.style.cssText = "position:absolute;pointer-events:none;";
    this._map.getPane("gribOverlay").appendChild(svg);
    this._isobarSvg = svg;
  }

  // Position a screen-space overlay SVG inside the (transformed) gribOverlay pane
  // so plain container-pixel drawing still lines up: place its top-left at the
  // layer point of the container's top-left corner, with a 0..size viewBox. The
  // pane's z-index (< popupPane) keeps click/meteogram popups above the overlay.
  _positionOverlaySvg(svg, size) {
    const tl = this._map.containerPointToLayerPoint([0, 0]);
    svg.setAttribute("width", size.x);
    svg.setAttribute("height", size.y);
    svg.setAttribute("viewBox", `0 0 ${size.x} ${size.y}`);
    svg.style.width = size.x + "px";
    svg.style.height = size.y + "px";
    svg.style.left = tl.x + "px";
    svg.style.top = tl.y + "px";
  }

  _removeIsobars() {
    if (this._isobarSvg) {
      this._isobarSvg.remove();
      this._isobarSvg = null;
    }
    this._isobarField = null;
  }

  _drawIsobars() {
    if (!this._isobarField || !this._isobarsOn) return;
    this._ensureIsobarSvg();
    const svg = this._isobarSvg;
    const svgns = "http://www.w3.org/2000/svg";
    [...svg.querySelectorAll("g")].forEach((el) => el.remove());
    const g = document.createElementNS(svgns, "g");
    const size = this._map.getSize();
    this._positionOverlaySvg(svg, size);

    const cfg = this._config || {};
    // Smooth the pressure field to a synoptic scale before contouring. The SAME
    // smoothed field feeds both the drawn isobars and the H/L detection, so they
    // stay consistent. `isobar_smoothing` is the scale in km (0 = off). The
    // default is moderate: heavier smoothing (e.g. 100-150) gives a cleaner
    // synoptic look but can flatten a centre near the domain edge until the
    // closed-isobar test drops it.
    const sigmaKm = cfg.isobar_smoothing == null ? 60 : Number(cfg.isobar_smoothing);
    const field = smoothField(this._isobarField, sigmaKm);
    let lo = Infinity;
    let hi = -Infinity;
    for (const v of field.data) {
      if (v != null && isFinite(v)) {
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    }
    if (!isFinite(lo) || hi <= lo) return;

    // Which isobars to draw. `isobar_levels` (explicit hPa list) wins; otherwise
    // every `isobar_interval` hPa (default 4 -- the synoptic standard; use e.g. 2
    // for denser lines). Only levels inside the field's range are kept.
    let levels;
    if (Array.isArray(cfg.isobar_levels) && cfg.isobar_levels.length) {
      levels = cfg.isobar_levels
        .map(Number)
        .filter((l) => isFinite(l) && l >= lo && l <= hi)
        .sort((a, b) => a - b);
    } else {
      const interval = Math.max(0.5, Number(cfg.isobar_interval) || 4);
      levels = [];
      for (let level = Math.ceil(lo / interval) * interval; level <= hi; level += interval) {
        levels.push(level);
      }
    }

    const proj = (lat, lon) => this._map.latLngToContainerPoint([lat, lon]);
    const cx = size.x / 2;
    const cy = size.y / 2;
    const placed = []; // label anchor points, to avoid clutter

    for (const level of levels) {
      const segs = marchingSquares(field, level);
      if (!segs.length) continue;
      let d = "";
      let best = null; // segment midpoint nearest screen centre -> label anchor
      for (const s of segs) {
        const p1 = proj(s[0], s[1]);
        const p2 = proj(s[2], s[3]);
        d += `M${p1.x.toFixed(1)},${p1.y.toFixed(1)}L${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
        const mx = (p1.x + p2.x) / 2;
        const my = (p1.y + p2.y) / 2;
        if (mx > 24 && mx < size.x - 24 && my > 16 && my < size.y - 16) {
          const dist = (mx - cx) ** 2 + (my - cy) ** 2;
          if (!best || dist < best.dist) best = { x: mx, y: my, dist };
        }
      }
      const bold = level % 20 === 0; // emphasise round 20-hPa isobars
      const casing = document.createElementNS(svgns, "path");
      casing.setAttribute("d", d);
      casing.setAttribute("fill", "none");
      casing.setAttribute("stroke", "#ffffff");
      casing.setAttribute("stroke-width", bold ? "3.4" : "2.6");
      casing.setAttribute("stroke-opacity", "0.7");
      casing.setAttribute("stroke-linejoin", "round");
      casing.setAttribute("stroke-linecap", "round");
      g.appendChild(casing);
      const line = document.createElementNS(svgns, "path");
      line.setAttribute("d", d);
      line.setAttribute("fill", "none");
      line.setAttribute("stroke", "#20344a");
      line.setAttribute("stroke-width", bold ? "1.7" : "1");
      line.setAttribute("stroke-linejoin", "round");
      line.setAttribute("stroke-linecap", "round");
      g.appendChild(line);

      // One value label per isobar, near screen centre, spaced from other labels.
      if (best && !placed.some((p) => (p.x - best.x) ** 2 + (p.y - best.y) ** 2 < 44 * 44)) {
        placed.push(best);
        const t = document.createElementNS(svgns, "text");
        t.setAttribute("x", best.x.toFixed(1));
        t.setAttribute("y", best.y.toFixed(1));
        t.setAttribute("text-anchor", "middle");
        t.setAttribute("dominant-baseline", "middle");
        t.setAttribute("font-family", "sans-serif");
        t.setAttribute("font-size", "11");
        t.setAttribute("font-weight", bold ? "700" : "600");
        t.setAttribute("fill", "#20344a");
        t.setAttribute("stroke", "#ffffff");
        t.setAttribute("stroke-width", "3");
        t.setAttribute("paint-order", "stroke");
        t.textContent = String(Math.round(level));
        g.appendChild(t);
      }
    }

    if (cfg.show_pressure_centres !== false) this._drawPressureCentres(field, g, proj, size);
    svg.appendChild(g);
  }

  // High (H) and Low (L) pressure centres on the SMOOTHED field, the way a
  // synoptic chart decides to print them (Hanley & Caballero 2012): a strict
  // local extremum that is enclosed by at least one closed isobar of interval
  // `pressure_prominence` (default = the isobar interval). Concretely we flood
  // from the extremum over cells within that interval of it; the centre counts
  // only if the flood stays bounded (doesn't reach the domain edge) and contains
  // no stronger cell. Survivors are then thinned by a ~400 km min-separation and
  // capped per type. This drops the mesoscale "wiggle" centres that a naive
  // local-extrema search prints.
  _drawPressureCentres(field, g, proj, size) {
    const svgns = "http://www.w3.org/2000/svg";
    const { nx, ny, lo1, la1, dx, dy, data } = field;
    const at = (x, y) => data[y * nx + x];
    const cfg = this._config || {};
    const interval = Math.max(0.5, Number(cfg.isobar_interval) || 4);
    const dP = Math.max(0.5, Number(cfg.pressure_prominence) || interval); // hPa
    const maxPerType = Math.max(1, Number(cfg.max_pressure_centres) || 4);
    const MIN_SEP_KM = 400;
    const KM_PER_DEG = 111.32;

    // Strict local extrema in a small window on the smoothed field.
    const R = 2;
    const cand = [];
    for (let y = R; y < ny - R; y++) {
      for (let x = R; x < nx - R; x++) {
        const c = at(x, y);
        if (c == null || !isFinite(c)) continue;
        let isMax = true;
        let isMin = true;
        for (let j = -R; j <= R && (isMax || isMin); j++) {
          for (let i = -R; i <= R; i++) {
            if (!i && !j) continue;
            const n = at(x + i, y + j);
            if (n == null || !isFinite(n)) continue;
            if (n > c) isMax = false;
            if (n < c) isMin = false;
          }
        }
        if (isMax === isMin) continue; // flat/saddle
        cand.push({ x, y, v: c, type: isMax ? "H" : "L" });
      }
    }

    // Closed-isobar test: flood from the extremum over cells within dP of it.
    const enclosed = (c) => {
      const thr = c.type === "H" ? c.v - dP : c.v + dP;
      const inside = (v) => (c.type === "H" ? v >= thr : v <= thr);
      const stronger = (v) => (c.type === "H" ? v > c.v + 1e-6 : v < c.v - 1e-6);
      const seen = new Set([c.y * nx + c.x]);
      const stack = [[c.x, c.y]];
      let touchedEdge = false;
      while (stack.length) {
        const [x, y] = stack.pop();
        if (x === 0 || x === nx - 1 || y === 0 || y === ny - 1) touchedEdge = true;
        for (const [ix, iy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
          const xx = x + ix;
          const yy = y + iy;
          if (xx < 0 || xx >= nx || yy < 0 || yy >= ny) continue;
          const idx = yy * nx + xx;
          if (seen.has(idx)) continue;
          const v = at(xx, yy);
          if (v == null || !isFinite(v)) continue;
          if (stronger(v)) return false; // a deeper/higher centre owns this basin
          if (inside(v)) {
            seen.add(idx);
            stack.push([xx, yy]);
          }
        }
      }
      return !touchedEdge;
    };

    const label = (px, py, text, color, fontSize, weight, halo) => {
      const t = document.createElementNS(svgns, "text");
      t.setAttribute("x", px.toFixed(1));
      t.setAttribute("y", py.toFixed(1));
      t.setAttribute("text-anchor", "middle");
      t.setAttribute("dominant-baseline", "central");
      t.setAttribute("font-family", "sans-serif");
      t.setAttribute("font-weight", weight);
      t.setAttribute("font-size", fontSize);
      t.setAttribute("fill", color);
      t.setAttribute("stroke", "#ffffff");
      t.setAttribute("stroke-width", halo);
      t.setAttribute("paint-order", "stroke");
      t.textContent = text;
      g.appendChild(t);
    };

    const geoKm = (a, b) => {
      const latA = la1 - a.y * dy;
      const latB = la1 - b.y * dy;
      const midLat = ((latA + latB) / 2) * (Math.PI / 180);
      const dLat = (latA - latB) * KM_PER_DEG;
      const dLon = (a.x - b.x) * dx * KM_PER_DEG * Math.cos(midLat);
      return Math.hypot(dLat, dLon);
    };

    for (const type of ["H", "L"]) {
      // Strongest first, keep only closed-isobar centres, thin by min separation.
      const ranked = cand
        .filter((c) => c.type === type && enclosed(c))
        .sort((a, b) => (type === "H" ? b.v - a.v : a.v - b.v));
      const chosen = [];
      for (const c of ranked) {
        if (chosen.some((q) => geoKm(q, c) < MIN_SEP_KM)) continue;
        chosen.push(c);
      }
      let drawn = 0;
      for (const c of chosen) {
        if (drawn >= maxPerType) break;
        const p = proj(la1 - c.y * dy, lo1 + c.x * dx);
        if (p.x < 14 || p.x > size.x - 14 || p.y < 18 || p.y > size.y - 18) continue;
        drawn++;
        const color = type === "H" ? "#1440a4" : "#d0021b";
        label(p.x, p.y, type, color, "20", "700", "3.5");
        label(p.x, p.y + 15, String(Math.round(c.v)), color, "10", "600", "2.6");
      }
    }
  }

  // -- point value (click) + meteogram (hold) --------------------------------

  async _fetchPointSeries(paramKey, latlng, entryId) {
    const id = entryId || this._currentEntry()?.entry_id;
    if (!id) return null;
    const q = `lat=${latlng.lat.toFixed(4)}&lon=${latlng.lng.toFixed(4)}`;
    return this._hass.callApi(
      "GET",
      `grib_overlay/point/${id}/${encodeURIComponent(paramKey)}?${q}`
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
          `<span style="opacity:.7">${formatTime(frame.valid_time)}</span>` +
          this._detailLinkHtml() +
          `</div>`
      )
      .openOn(this._map);
    this._wireDetailLink(latlng);
  }

  async _onMapHold(latlng) {
    const paramKey = this._els.paramSelect.value;
    if (!paramKey || !this._frames.length) return;

    // Wind + gusts share the same speed unit; when both are configured, show
    // them together (wind line + gust envelope) on one meteogram.
    const pair = this._windGustPair(paramKey);
    try {
      if (pair) {
        const [windResp, gustResp] = await Promise.all([
          this._fetchPointSeries(pair.windKey, latlng),
          this._fetchPointSeries(pair.gustKey, latlng),
        ]);
        const windSeries = (windResp && windResp.series) || [];
        if (!windSeries.some((s) => s.value != null)) return;
        const hasDir =
          !!(windResp && windResp.direction_unit) && windSeries.some((s) => s.direction != null);
        const svg = this._buildMeteogram(windSeries, windResp.unit, latlng, {
          hasDirection: hasDir,
          overlay: { series: (gustResp && gustResp.series) || [], label: "windstoten" },
          title: this._paramLabel(pair.windKey),
        });
        this._openMeteogramPopup(latlng, svg);
        return;
      }

      const resp = await this._fetchPointSeries(paramKey, latlng);
      const series = (resp && resp.series) || [];
      if (!series.some((s) => s.value != null)) return;
      const hasDir = !!(resp && resp.direction_unit) && series.some((s) => s.direction != null);
      const svg = this._buildMeteogram(series, resp.unit, latlng, { hasDirection: hasDir });
      this._openMeteogramPopup(latlng, svg);
    } catch (err) {
      return;
    }
  }

  // When the meteogram parameter is wind (or gusts) and both are configured on
  // this entry, returns the two keys so the meteogram can combine them; else null.
  _windGustPair(paramKey) {
    if (paramKey !== "wind_10m" && paramKey !== "wind_gust_10m") return null;
    const entry = this._currentEntry();
    if (!entry) return null;
    const has = (k) => entry.parameters.some((p) => p.key === k);
    if (!has("wind_10m") || !has("wind_gust_10m")) return null;
    return { windKey: "wind_10m", gustKey: "wind_gust_10m" };
  }

  _paramLabel(paramKey) {
    const entry = this._currentEntry();
    const p = entry && entry.parameters.find((x) => x.key === paramKey);
    return p ? p.name : paramKey;
  }

  _openMeteogramPopup(latlng, svg) {
    this._pointPopup = window.L.popup({
      closeButton: true,
      autoPan: true,
      maxWidth: 340,
      className: "grib-meteogram-popup",
    })
      .setLatLng(latlng)
      .setContent(svg)
      .openOn(this._map);
    this._wireDetailLink(latlng);
  }

  // Link markup (shared by the value + meteogram popups) that opens the full
  // meteogram. Only shown when there's more than one series worth combining.
  _detailLinkHtml() {
    const paramCount = (this._entries || []).reduce((n, e) => n + (e.parameters || []).length, 0);
    if (paramCount <= 1) return "";
    return (
      `<a href="#" class="grib-meteogram-more" style="display:block;margin-top:5px;` +
      `font-size:12px;color:var(--primary-color,#0288d1);text-decoration:none;cursor:pointer">` +
      `Alle parameters &amp; bronnen &#9656;</a>`
    );
  }

  // After a popup opens, wire its "all parameters" link to the full meteogram.
  _wireDetailLink(latlng) {
    const el = this._pointPopup && this._pointPopup.getElement && this._pointPopup.getElement();
    const more = el && el.querySelector(".grib-meteogram-more");
    if (more) {
      more.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        this._openDetailMeteogram(latlng);
      });
    }
  }

  _buildMeteogram(series, sourceUnit, latlng, { hasDirection = false, overlay = null, title = null } = {}) {
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

    // Optional second series (wind gusts): match each primary time to the gust
    // value (same left/speed axis, drawn as a line + envelope band) and the gust
    // from-direction (same right/direction axis, drawn as a second line).
    let gustPts = null;
    if (overlay && overlay.series) {
      const gustByT = new Map(
        overlay.series
          .filter((s) => s.value != null)
          .map((s) => [new Date(s.valid_time).getTime(), s.value * factor])
      );
      const gustDirByT = new Map(
        overlay.series
          .filter((s) => s.direction != null)
          .map((s) => [new Date(s.valid_time).getTime(), s.direction])
      );
      const aligned = pts
        .map((p) => ({
          t: p.t,
          v: p.v,
          g: gustByT.has(p.t) ? gustByT.get(p.t) : null,
          gdir: gustDirByT.has(p.t) ? gustDirByT.get(p.t) : null,
        }))
        .filter((p) => p.g != null);
      if (aligned.length) gustPts = aligned;
    }
    const showGustDir = !!(gustPts && gustPts.some((p) => p.gdir != null));
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
      if (gustPts) vals.push(...gustPts.map((p) => p.g)); // gusts sit above wind
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
      // Gust from-direction on the same axis: a lighter, finely-dotted line with
      // hollow dots, so it reads as the "gust" companion of the wind direction.
      if (showGustDir) {
        let gdpath = "";
        let gprev = null;
        for (const p of gustPts) {
          if (p.gdir == null) {
            gprev = null;
            continue;
          }
          const cmd = gprev == null || Math.abs(p.gdir - gprev) > 180 ? "M" : "L";
          gdpath += `${cmd}${sx(p.t).toFixed(1)},${sy2(p.gdir).toFixed(1)}`;
          gprev = p.gdir;
        }
        parts.push(
          `<path d="${gdpath}" fill="none" stroke="${DIR_COLOR}" stroke-width="1.3" stroke-dasharray="1.5 2.5" opacity="0.8"/>`
        );
        parts.push(
          gustPts
            .filter((p) => p.gdir != null)
            .map((p) => `<circle cx="${sx(p.t).toFixed(1)}" cy="${sy2(p.gdir).toFixed(1)}" r="1.6" fill="none" stroke="${DIR_COLOR}" stroke-width="1" opacity="0.8"/>`)
            .join("")
        );
      }
    }

    // Wind-gust envelope: a light band between wind and gust speed, plus a
    // dashed gust line, drawn under the wind line so the wind stays prominent.
    if (gustPts) {
      const up = gustPts.map((p, i) => `${i ? "L" : "M"}${sx(p.t).toFixed(1)},${sy(p.g).toFixed(1)}`).join(" ");
      const down = gustPts
        .slice()
        .reverse()
        .map((p) => `L${sx(p.t).toFixed(1)},${sy(p.v).toFixed(1)}`)
        .join(" ");
      parts.push(
        `<path d="${up} ${down} Z" fill="var(--primary-color,#03a9f4)" fill-opacity="0.12" stroke="none"/>`
      );
      const gline = gustPts.map((p, i) => `${i ? "L" : "M"}${sx(p.t).toFixed(1)},${sy(p.g).toFixed(1)}`).join(" ");
      parts.push(
        `<path d="${gline}" fill="none" stroke="var(--primary-color,#03a9f4)" stroke-width="1.5" stroke-dasharray="3 2" opacity="0.85"/>`
      );
      parts.push(
        gustPts
          .map((p) => `<circle cx="${sx(p.t).toFixed(1)}" cy="${sy(p.g).toFixed(1)}" r="1.8" fill="var(--primary-color,#03a9f4)" opacity="0.85"/>`)
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
    const legendItems = [
      `<span style="color:var(--primary-color,#03a9f4)">━ ${primaryLabel} (${unit})</span>`,
    ];
    if (gustPts) {
      legendItems.push(
        `<span style="color:var(--primary-color,#03a9f4);opacity:.85">╌ ${overlay.label} (${unit})</span>`
      );
    }
    if (showDir) {
      const dirUnit = dirMode === "deg" ? "°" : "kompas";
      legendItems.push(
        `<span style="color:${DIR_COLOR}">┅ ${showGustDir ? "windrichting" : "richting"} (${dirUnit})</span>`
      );
      if (showGustDir) {
        legendItems.push(`<span style="color:${DIR_COLOR};opacity:.8">⋯ stoot-richting</span>`);
      }
    }
    const legend =
      gustPts || showDir
        ? `<div style="font-size:11px;margin-top:1px">${legendItems.join("&nbsp;&nbsp;")}</div>`
        : "";
    const moreLink = this._detailLinkHtml();
    return (
      `<div style="width:290px;max-width:78vw;font:14px sans-serif"><b>${title || this._paramName()}</b> · ${unit}` +
      `<div style="opacity:.6;font-size:12px">${latlng.lat.toFixed(2)}, ${latlng.lng.toFixed(2)}</div>` +
      legend +
      `<svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block;margin-top:4px">` +
      parts.join("") +
      `</svg>` +
      moreLink +
      `</div>`
    );
  }

  // -- detailed meteogram (all parameters, every source) ----------------------

  // Full meteogram: every parameter of every configured entry (KNMI, DWD, BSH,
  // ...) sampled at this point, laid out as a Windy-style table -- one row per
  // parameter, colour-coded value cells, all sharing a single time-column axis.
  async _openDetailMeteogram(latlng) {
    const entries = this._entries || [];
    if (!entries.length) return;
    this._openDetailModal(latlng);

    // One batch request per entry (all parameters + legends in a single round
    // trip). Entries whose grid doesn't cover this point return all-null series
    // and are dropped when the table is built.
    let groups;
    try {
      groups = await Promise.all(entries.map((entry) => this._fetchEntryPointData(entry, latlng)));
    } catch (err) {
      this._setDetailBody(`<div class="grib-detail-loading">Kon meteogram niet laden.</div>`);
      return;
    }
    if (!this._detailModal) return; // closed while loading
    this._setDetailBody(this._buildDetailTable(groups, latlng));
    // Apply the configured default selection: rows whose parameter isn't in the
    // list start hidden (the user can still bring any back via the chips).
    const sel = this._meteogramSelection();
    if (sel) {
      for (const grp of this._detailRowNames.keys()) {
        const key = grp.slice(grp.indexOf("::") + 2);
        if (!sel.has(key)) this._detailHidden.add(grp);
      }
    }
    this._applyDetailHidden();
  }

  // All parameters (series + colour legend) for one entry at a point. Uses the
  // batch endpoint (one request); falls back to the frames + per-parameter point
  // requests for integrations that predate `point_all`.
  async _fetchEntryPointData(entry, latlng) {
    const params = entry.parameters || [];
    const q = `lat=${latlng.lat.toFixed(4)}&lon=${latlng.lng.toFixed(4)}`;
    try {
      const data = await this._hass.callApi(
        "GET",
        `grib_overlay/point_all/${entry.entry_id}?${q}`
      );
      const byKey = (data && data.params) || {};
      const seriesByKey = new Map();
      const legendByKey = {};
      for (const p of params) {
        const pr = byKey[p.key] || null;
        seriesByKey.set(p.key, pr);
        legendByKey[p.key] = (pr && pr.legend) || null;
      }
      return { entry, seriesByKey, legendByKey };
    } catch (err) {
      const [framesAll, seriesEntries] = await Promise.all([
        this._hass.callApi("GET", `grib_overlay/frames/${entry.entry_id}`).catch(() => ({})),
        Promise.all(
          params.map((p) =>
            this._fetchPointSeries(p.key, latlng, entry.entry_id)
              .then((r) => [p.key, r])
              .catch(() => [p.key, null])
          )
        ),
      ]);
      const legendByKey = {};
      for (const p of params) {
        const frames = framesAll[p.key];
        legendByKey[p.key] = (frames && frames[0] && frames[0].legend) || null;
      }
      return { entry, seriesByKey: new Map(seriesEntries), legendByKey };
    }
  }

  // The card's configured default meteogram row selection: a set of parameter
  // keys to show (list or comma/space-separated string), or null to show all.
  _meteogramSelection() {
    const cfg = this._config || {};
    const raw = cfg.meteogram_parameters ?? cfg.meteogram_params;
    if (raw == null) return null;
    const list = Array.isArray(raw) ? raw : String(raw).split(/[\s,]+/);
    const set = new Set(list.map((s) => String(s).trim()).filter(Boolean));
    return set.size ? set : null;
  }

  _openDetailModal(latlng) {
    this._closeDetailMeteogram();
    this._detailHidden = new Set(); // rows the user has temporarily hidden
    this._detailRowNames = new Map();
    const backdrop = document.createElement("div");
    backdrop.className = "grib-detail-backdrop";
    backdrop.innerHTML =
      `<div class="grib-detail-modal">` +
      `<div class="grib-detail-head">` +
      `<span class="grib-detail-title">Meteogram</span>` +
      `<span class="grib-detail-sub">${latlng.lat.toFixed(3)}, ${latlng.lng.toFixed(3)} · alle bronnen</span>` +
      `<button class="grib-detail-close" title="Sluiten" aria-label="Sluiten">&#10005;</button>` +
      `</div>` +
      `<div class="grib-detail-tools">` +
      `<span class="hint">Tik een rijlabel om die rij te verbergen</span>` +
      `<span class="chips"></span>` +
      `<button class="showall hidden">Alle rijen tonen</button>` +
      `</div>` +
      `<div class="grib-detail-scroll"><div class="grib-detail-loading">` +
      `<span class="grib-spinner" aria-hidden="true"></span>` +
      `<span>Meteogram voorbereiden…</span></div></div>` +
      `</div>`;
    backdrop.addEventListener("click", (ev) => {
      if (ev.target === backdrop) this._closeDetailMeteogram();
    });
    backdrop
      .querySelector(".grib-detail-close")
      .addEventListener("click", () => this._closeDetailMeteogram());
    // Click a row label to hide that parameter; click a chip to bring it back.
    backdrop.querySelector(".grib-detail-scroll").addEventListener("click", (ev) => {
      const label = ev.target.closest("td.rowlabel[data-grp]");
      if (label) this._toggleDetailRow(label.getAttribute("data-grp"));
    });
    backdrop.querySelector(".chips").addEventListener("click", (ev) => {
      const chip = ev.target.closest(".chip[data-grp]");
      if (chip) this._toggleDetailRow(chip.getAttribute("data-grp"));
    });
    backdrop.querySelector(".showall").addEventListener("click", () => {
      this._detailHidden.clear();
      this._applyDetailHidden();
    });
    this._detailEsc = (ev) => {
      if (ev.key === "Escape") this._closeDetailMeteogram();
    };
    document.addEventListener("keydown", this._detailEsc);
    this.shadowRoot.appendChild(backdrop);
    this._detailModal = backdrop;
  }

  // Show/hide one parameter's rows (its value row plus any direction row).
  _toggleDetailRow(grp) {
    if (!grp) return;
    if (this._detailHidden.has(grp)) this._detailHidden.delete(grp);
    else this._detailHidden.add(grp);
    this._applyDetailHidden();
  }

  // Apply the current hidden set to the table + refresh the tools bar.
  _applyDetailHidden() {
    if (!this._detailModal) return;
    const hidden = this._detailHidden || new Set();
    this._detailModal.querySelectorAll(".grib-detail-table td.rowlabel[data-grp]").forEach((td) => {
      const tr = td.closest("tr");
      if (tr) tr.style.display = hidden.has(td.getAttribute("data-grp")) ? "none" : "";
    });
    const list = [...hidden];
    const chips = this._detailModal.querySelector(".grib-detail-tools .chips");
    const hint = this._detailModal.querySelector(".grib-detail-tools .hint");
    const showall = this._detailModal.querySelector(".grib-detail-tools .showall");
    if (chips) {
      chips.innerHTML = list
        .map(
          (grp) =>
            `<button class="chip" data-grp="${grp}" title="Weer tonen">` +
            `${this._detailRowNames.get(grp) || grp} &#43;</button>`
        )
        .join("");
    }
    if (hint) hint.classList.toggle("hidden", list.length > 0);
    if (showall) showall.classList.toggle("hidden", list.length === 0);
  }

  _setDetailBody(html) {
    if (!this._detailModal) return;
    const scroll = this._detailModal.querySelector(".grib-detail-scroll");
    if (scroll) scroll.innerHTML = html;
  }

  _closeDetailMeteogram() {
    if (this._detailEsc) {
      document.removeEventListener("keydown", this._detailEsc);
      this._detailEsc = null;
    }
    if (this._detailModal) {
      this._detailModal.remove();
      this._detailModal = null;
    }
  }

  _buildDetailTable(groups, latlng) {
    // Keep only entries that actually have data at this point. Sources that are
    // configured but return nothing here (e.g. BSH's North-Sea-only grid when
    // the click is inland, or a source still downloading) are dropped, and then
    // named in a footer note so their absence is explained rather than silent.
    const all = (groups || []).filter(Boolean);
    const active = all.filter((g) =>
      [...g.seriesByKey.values()].some(
        (r) => r && r.series && r.series.some((s) => s.value != null)
      )
    );
    const note = this._droppedSourcesNote(all.filter((g) => !active.includes(g)));
    if (!active.length) {
      return `<div class="grib-detail-loading">Geen gegevens beschikbaar op dit punt.</div>` + note;
    }

    // Shared time axis = union of all valid_times across every source, sorted.
    const timeSet = new Set();
    for (const g of active) {
      for (const r of g.seriesByKey.values()) {
        if (r && r.series) {
          for (const s of r.series) if (s.value != null) timeSet.add(s.valid_time);
        }
      }
    }
    const times = [...timeSet].sort();
    const dates = times.map((t) => new Date(t));

    // Day boundaries (for separators/grouped day headers) + "now" column.
    const sepAt = dates.map((d, i) => i > 0 && d.toDateString() !== dates[i - 1].toDateString());
    const now = Date.now();
    let nowIdx = -1;
    let nowBest = Infinity;
    dates.forEach((d, i) => {
      const gap = Math.abs(d.getTime() - now);
      if (gap < nowBest) {
        nowBest = gap;
        nowIdx = i;
      }
    });
    if (nowBest > 3 * 3600000) nowIdx = -1; // only mark "now" if the run spans it
    const cls = (i) => `cell${sepAt[i] ? " daysep" : ""}${i === nowIdx ? " nowcol" : ""}`;

    // Header: a day row (weekday spanning its hours) + an hour row.
    const dayFmt = new Intl.DateTimeFormat("nl-NL", { weekday: "short", day: "numeric", month: "short" });
    let dayRow = `<th class="rowlabel"></th>`;
    for (let i = 0; i < times.length; ) {
      let span = 1;
      while (i + span < times.length && dates[i + span].toDateString() === dates[i].toDateString()) {
        span++;
      }
      dayRow += `<th colspan="${span}" class="dayhead${i > 0 ? " daysep" : ""}">${dayFmt.format(dates[i])}</th>`;
      i += span;
    }
    let hourRow = `<th class="rowlabel">tijd</th>`;
    times.forEach((t, i) => {
      const hh = String(dates[i].getHours()).padStart(2, "0");
      hourRow += `<th class="${cls(i)}">${hh}</th>`;
    });

    const ctx = { times, cls, colCount: times.length };
    const body = active.map((g) => this._buildEntryRows(g, ctx)).join("");
    return (
      `<table class="grib-detail-table">` +
      `<thead><tr>${dayRow}</tr><tr>${hourRow}</tr></thead>` +
      `<tbody>${body}</tbody></table>` +
      note
    );
  }

  // A footer note naming configured sources that returned no data at this point,
  // so a missing source (e.g. BSH outside its North-Sea grid) is explained. A
  // source with frames but only null samples is "buiten bereik" (out of grid);
  // one with no frames at all is "nog geen data" (still downloading/empty).
  _droppedSourcesNote(dropped) {
    if (!dropped || !dropped.length) return "";
    const items = dropped.map((g) => {
      const src = String(g.entry.source || "").toUpperCase();
      const name = (g.entry.dataset && g.entry.dataset.name) || g.entry.title || src || "bron";
      const hasFrames = [...g.seriesByKey.values()].some((r) => r && r.series && r.series.length);
      const reason = hasFrames ? "buiten bereik op dit punt" : "nog geen data";
      return `${src ? src + " · " : ""}${name} (${reason})`;
    });
    return `<div class="grib-detail-note">Niet getoond: ${items.join("; ")}</div>`;
  }

  // Rows for one entry: a source/dataset header, then a colour-coded value row
  // per parameter (with a wind/wave from-direction arrow row above where present).
  _buildEntryRows(group, { times, cls, colCount }) {
    const { entry, seriesByKey, legendByKey } = group;
    const rows = [];
    const src = String(entry.source || "").toUpperCase();
    const dsName = (entry.dataset && entry.dataset.name) || entry.title || src || "bron";
    const suffix = entry.title && entry.title !== dsName ? ` · ${entry.title}` : "";
    rows.push(
      `<tr class="grouprow">` +
        `<td class="rowlabel grouplabel"><span class="src">${src || "GRIB"}</span></td>` +
        `<td class="grouphead" colspan="${colCount}">${dsName}${suffix}</td></tr>`
    );

    for (const p of entry.parameters || []) {
      const resp = seriesByKey.get(p.key);
      if (!resp || !resp.series || !resp.series.some((s) => s.value != null)) continue;
      if (p.unit === "°") continue; // a standalone direction is drawn as arrows on its companion

      const byT = new Map(resp.series.map((s) => [s.valid_time, s]));
      const conv = this._conversionFor(resp.unit);
      const factor = conv ? conv.factor : 1;
      const dispUnit = conv ? conv.label : resp.unit;
      const legend = legendByKey[p.key];
      // A per-parameter id so a row (and its direction companion) can be hidden.
      const grp = `${entry.entry_id}::${p.key}`;
      if (this._detailRowNames) this._detailRowNames.set(grp, `${src} · ${p.name}`);

      // Direction arrow row: the arrow points the way the wind/waves travel, with
      // the from-direction printed below it in the card's chosen unit (compass or
      // 0-360 degrees), so it reads both at a glance and exactly.
      if (resp.direction_unit && resp.series.some((s) => s.direction != null)) {
        let cells = `<td class="rowlabel" data-grp="${grp}" title="Klik om te verbergen">${p.name}<span class="ru">richting</span></td>`;
        times.forEach((t, i) => {
          const s = byT.get(t);
          if (s && s.direction != null) {
            const toDir = ((s.direction + 180) % 360).toFixed(0);
            const label = this._formatDirection(s.direction);
            const title = `${compass(s.direction)} (${Math.round(s.direction)}°)`;
            cells +=
              `<td class="${cls(i)} arrowcell" title="${title}">` +
              `<span class="arw" style="transform:rotate(${toDir}deg)">&#8593;</span>` +
              `<span class="dirnum">${label}</span></td>`;
          } else {
            cells += `<td class="${cls(i)}"></td>`;
          }
        });
        rows.push(`<tr class="windrow">${cells}</tr>`);
      }

      // Value row: each cell tinted by the parameter's own colour scale.
      let cells = `<td class="rowlabel" data-grp="${grp}" title="Klik om te verbergen">${p.name}<span class="ru">${dispUnit}</span></td>`;
      times.forEach((t, i) => {
        const s = byT.get(t);
        if (s && s.value != null) {
          const bg = legend ? this._lerpLegendColor(legend, s.value) : null;
          const style = bg ? ` style="background:${bg};color:${this._readableText(bg)}"` : "";
          cells += `<td class="${cls(i)}"${style}>${this._fmtCell(resp.unit, s.value * factor)}</td>`;
        } else {
          cells += `<td class="${cls(i)}">–</td>`;
        }
      });
      rows.push(`<tr class="valrow">${cells}</tr>`);
    }
    return rows.join("");
  }

  // Interpolate a legend gradient (stops in the field's source unit) at a value.
  _lerpLegendColor(legend, value) {
    if (!legend || !legend.stops || !legend.stops.length) return null;
    const span = legend.max_value - legend.min_value || 1;
    let f = (value - legend.min_value) / span;
    f = Math.max(0, Math.min(1, f));
    const stops = legend.stops;
    let a = stops[0];
    let b = stops[stops.length - 1];
    for (let i = 0; i < stops.length - 1; i++) {
      if (f >= stops[i].offset && f <= stops[i + 1].offset) {
        a = stops[i];
        b = stops[i + 1];
        break;
      }
    }
    const t = b.offset === a.offset ? 0 : (f - a.offset) / (b.offset - a.offset);
    const ca = hexToRgb(a.color);
    const cb = hexToRgb(b.color);
    const mix = (k) => Math.round(ca[k] + (cb[k] - ca[k]) * t);
    return `rgb(${mix(0)},${mix(1)},${mix(2)})`;
  }

  // Pick dark or light text for legibility against a cell's fill colour.
  _readableText(rgb) {
    const m = /(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/.exec(rgb || "");
    if (!m) return "var(--primary-text-color,#12324f)";
    const lum = (0.299 * +m[1] + 0.587 * +m[2] + 0.114 * +m[3]) / 255;
    return lum > 0.62 ? "#12324f" : "#ffffff";
  }

  // Format a display value for a table cell (decimals scaled to the unit).
  _fmtCell(sourceUnit, v) {
    if (v == null || !Number.isFinite(v)) return "–";
    if (sourceUnit === "°C" || sourceUnit === "hPa" || sourceUnit === "%") return String(Math.round(v));
    if (sourceUnit === "mm") return v < 0.05 ? "–" : v.toFixed(1);
    return (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1)).replace(/\.0$/, "");
  }

  _onRenderModeChange() {
    const v = this._els.renderModeSelect.value;
    this._renderMode = RENDER_MODES.includes(v) ? v : "raster";
    if (this._frames.length) this._showFrame(this._frameIndex || 0);
  }

  _onIsobarsToggle() {
    this._isobarsOn = this._els.isobarsToggle.checked;
    if (this._frames.length) this._showFrame(this._frameIndex || 0);
  }

  // Enable/disable overlays based on the available data: wind modes need a wind
  // (u/v) parameter, the wave-arrow mode a wave-direction parameter, and the
  // isobars layer a mean-sea-level pressure parameter on the current dataset.
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

    // The isobars layer is available whenever the dataset carries pressure.
    const hasPressure = !!this._pressureParam();
    this._els.isobarsToggle.disabled = !hasPressure;
    this._els.isobarsToggleLabel.style.opacity = hasPressure ? "" : "0.4";
    this._els.isobarsToggle.checked = this._isobarsOn && hasPressure;
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
