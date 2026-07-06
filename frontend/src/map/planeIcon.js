import L from "leaflet";

// A single top-pointing airplane silhouette. Because the SVG points "north"
// (0deg), rotating the wrapper by the aircraft's true_track makes it face the
// correct heading.
const PLANE_SVG = `
<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
  <path d="M12 2c-.6 0-1 .8-1 1.8v5.2L3 14v2l8-2.2V19l-2 1.2V22l3-1 3 1v-1.8L13 19v-5.2l8 2.2v-2l-8-4.8V3.8C13 2.8 12.6 2 12 2z"/>
</svg>`;

/**
 * Build the divIcon used for every plane marker. The outer div is the wrapper we
 * rotate; keeping a stable structure lets us update rotation by writing to the
 * element's style rather than recreating the icon on every tick.
 */
export function makePlaneIcon(track, onGround) {
  const rot = Number.isFinite(track) ? track : 0;
  const cls = onGround ? "plane-marker on-ground" : "plane-marker";
  return L.divIcon({
    className: "",
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    html: `<div class="${cls}" style="transform: rotate(${rot}deg)">${PLANE_SVG}</div>`,
  });
}

/**
 * Rotate an already-rendered marker in place (cheap path used during animation).
 * Falls back silently if the element isn't in the DOM yet.
 */
export function setMarkerRotation(marker, track, onGround) {
  const el = marker.getElement();
  if (!el) return;
  const wrapper = el.querySelector(".plane-marker");
  if (!wrapper) return;
  const rot = Number.isFinite(track) ? track : 0;
  wrapper.style.transform = `rotate(${rot}deg)`;
  wrapper.classList.toggle("on-ground", !!onGround);
}
