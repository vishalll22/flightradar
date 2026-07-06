import { useEffect, useRef } from "react";
import L from "leaflet";
import { PlaneLayer } from "./planeLayer.js";
import { useFlightSocket } from "../hooks/useFlightSocket.js";

// CartoDB Dark Matter — free, no API key, and dark so the bright planes pop.
const DARK_TILES = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const TILE_ATTRIB =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> ' +
  '&copy; <a href="https://carto.com/attributions">CARTO</a> · ADS-B via OpenSky';

function boundsToBbox(map) {
  const b = map.getBounds();
  // [south, west, north, east]
  return [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()];
}

/**
 * The map surface. Owns the Leaflet instance, the plane layer, the WebSocket
 * subscription, and the animation loop. Reports plane count + connection state
 * upward via callbacks so the HUD can render outside the map.
 */
export default function MapView({ onCount, onConnected }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const layerRef = useRef(null);

  const { connected, subscribe } = useFlightSocket((delta) => {
    if (!layerRef.current) return;
    layerRef.current.applyDelta(delta, performance.now());
    onCount?.(layerRef.current.count);
  });

  // Keep the parent's connection indicator in sync.
  useEffect(() => {
    onConnected?.(connected);
  }, [connected, onConnected]);

  useEffect(() => {
    const map = L.map(containerRef.current, {
      center: [51.47, 0.0], // London-ish
      zoom: 8,
      worldCopyJump: true,
    });
    L.tileLayer(DARK_TILES, { attribution: TILE_ATTRIB, maxZoom: 18 }).addTo(map);

    const layer = new PlaneLayer(map);
    mapRef.current = map;
    layerRef.current = layer;

    // Subscribe to whatever region is visible, debounced so a drag doesn't spam.
    let moveTimer = null;
    const pushBbox = () => subscribe(boundsToBbox(map));
    const onMove = () => {
      clearTimeout(moveTimer);
      moveTimer = setTimeout(pushBbox, 250);
    };
    map.on("moveend", onMove);
    map.whenReady(pushBbox);

    // Animation loop: extrapolate positions every frame for smooth motion.
    let raf = 0;
    const tick = () => {
      layer.step(performance.now());
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(moveTimer);
      map.off("moveend", onMove);
      layer.destroy();
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div id="map" ref={containerRef} />;
}
