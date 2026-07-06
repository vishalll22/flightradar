import L from "leaflet";
import { makePlaneIcon, setMarkerRotation } from "./planeIcon.js";
import { deadReckon } from "../lib/interpolate.js";

/**
 * Manages the set of plane markers on a Leaflet map, keyed by icao24.
 *
 * Server deltas (added/updated/removed) mutate an authoritative record per plane;
 * a separate animation step() extrapolates positions between updates so markers
 * move smoothly. This separation is exactly the "state dictionary" pattern: one
 * marker per aircraft, created/updated/removed as it enters, moves, and leaves.
 */
export class PlaneLayer {
  constructor(map) {
    this.map = map;
    this.layer = L.layerGroup().addTo(map);
    // icao24 -> { marker, state, t0 (ms when state became authoritative) }
    this.planes = new Map();
  }

  get count() {
    return this.planes.size;
  }

  _label(s) {
    const alt = s.geo_altitude != null ? `${Math.round(s.geo_altitude)} m` : "—";
    const spd = s.velocity != null ? `${Math.round(s.velocity)} m/s` : "—";
    return `${(s.callsign || s.icao24).trim()} · ${alt} · ${spd}`;
  }

  _add(s, now) {
    const marker = L.marker([s.latitude, s.longitude], {
      icon: makePlaneIcon(s.true_track, s.on_ground),
      interactive: true,
    });
    marker.bindTooltip(this._label(s), {
      className: "plane-tip",
      direction: "top",
      offset: [0, -10],
    });
    marker.addTo(this.layer);
    this.planes.set(s.icao24, { marker, state: s, t0: now });
  }

  _update(s, now) {
    const rec = this.planes.get(s.icao24);
    if (!rec) return this._add(s, now);
    rec.state = s;
    rec.t0 = now; // reset the extrapolation clock to this authoritative fix
    setMarkerRotation(rec.marker, s.true_track, s.on_ground);
    rec.marker.setTooltipContent(this._label(s));
  }

  _remove(icao24) {
    const rec = this.planes.get(icao24);
    if (!rec) return;
    this.layer.removeLayer(rec.marker);
    this.planes.delete(icao24);
  }

  /** Apply a server delta message. `now` is a ms timestamp (performance.now()). */
  applyDelta(delta, now) {
    for (const s of delta.added || []) this._add(s, now);
    for (const s of delta.updated || []) this._update(s, now);
    for (const id of delta.removed || []) this._remove(id);
  }

  /** Replace the entire set (used for the initial REST/snapshot paint). */
  reset(states, now) {
    this.layer.clearLayers();
    this.planes.clear();
    for (const s of states) this._add(s, now);
  }

  /**
   * Advance every marker to its extrapolated position. Call once per animation
   * frame with performance.now().
   */
  step(now) {
    for (const rec of this.planes.values()) {
      const s = rec.state;
      if (s.on_ground || !s.velocity) continue;
      const elapsed = (now - rec.t0) / 1000;
      const { lat, lon } = deadReckon(
        s.latitude,
        s.longitude,
        s.velocity,
        s.true_track,
        elapsed
      );
      rec.marker.setLatLng([lat, lon]);
    }
  }

  destroy() {
    this.map.removeLayer(this.layer);
    this.planes.clear();
  }
}
