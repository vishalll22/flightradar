// Dead-reckoning helpers: between the ~5-10s server updates we extrapolate each
// plane's position from its last known state so it glides instead of jumping.

const METERS_PER_DEG_LAT = 111320;

/**
 * Project a position forward along a heading.
 *
 * @param {number} lat      last known latitude (deg)
 * @param {number} lon      last known longitude (deg)
 * @param {number} velocity ground speed (m/s)
 * @param {number} track    heading, degrees clockwise from north
 * @param {number} elapsed  seconds since the last known position
 * @returns {{lat:number, lon:number}}
 */
export function deadReckon(lat, lon, velocity, track, elapsed) {
  if (!velocity || !Number.isFinite(track) || elapsed <= 0) {
    return { lat, lon };
  }
  const dist = velocity * elapsed; // meters travelled
  const rad = (track * Math.PI) / 180;
  const north = dist * Math.cos(rad);
  const east = dist * Math.sin(rad);

  const dLat = north / METERS_PER_DEG_LAT;
  const cosLat = Math.cos((lat * Math.PI) / 180);
  const dLon = east / (METERS_PER_DEG_LAT * Math.max(cosLat, 1e-6));

  return { lat: lat + dLat, lon: lon + dLon };
}
