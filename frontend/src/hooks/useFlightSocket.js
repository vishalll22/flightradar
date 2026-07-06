import { useEffect, useRef, useState } from "react";

// Resolve the WebSocket URL: explicit env override, else same-origin /ws (works
// with the Vite dev proxy and with a single-origin production deploy).
function wsUrl() {
  const override = import.meta.env.VITE_WS_URL;
  if (override) return override;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

/**
 * Maintain a WebSocket to the flight stream with auto-reconnect.
 *
 * @param onDelta  called with each {type:'update', added, updated, removed} message
 * @returns { connected, subscribe(bbox) } where bbox is [south, west, north, east]
 */
export function useFlightSocket(onDelta) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const bboxRef = useRef(null); // last requested bbox, re-sent on (re)connect
  const onDeltaRef = useRef(onDelta);
  const retryRef = useRef(null);

  onDeltaRef.current = onDelta;

  useEffect(() => {
    let closedByUs = false;

    const connect = () => {
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        // Re-subscribe to the current view after a reconnect.
        if (bboxRef.current) {
          ws.send(JSON.stringify({ type: "subscribe", bbox: bboxRef.current }));
        }
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "update") onDeltaRef.current?.(msg);
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closedByUs) retryRef.current = setTimeout(connect, 1500);
      };
      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      closedByUs = true;
      clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, []);

  const subscribe = (bbox) => {
    bboxRef.current = bbox;
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "subscribe", bbox }));
    }
  };

  return { connected, subscribe };
}
