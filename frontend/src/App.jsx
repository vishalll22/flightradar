import { useCallback, useState } from "react";
import MapView from "./map/MapView.jsx";

export default function App() {
  const [count, setCount] = useState(0);
  const [connected, setConnected] = useState(false);

  // Stable callbacks so MapView's effect doesn't tear down on every render.
  const onCount = useCallback((n) => setCount(n), []);
  const onConnected = useCallback((c) => setConnected(c), []);

  return (
    <>
      <MapView onCount={onCount} onConnected={onConnected} />
      <div className="hud">
        <h1>✈ Flight Radar</h1>
        <div className="stat">
          <span>
            <span className={`status-dot ${connected ? "connected" : "disconnected"}`} />
            {connected ? "Live" : "Reconnecting…"}
          </span>
        </div>
        <div className="stat">
          <span>Aircraft in view</span>
          <b>{count}</b>
        </div>
      </div>
    </>
  );
}
