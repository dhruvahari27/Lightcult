import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api, type AlertDetail, type InterceptResult } from "../lib/api";
import { sound } from "../lib/sound";

interface Props {
  alert: AlertDetail;
  onInterceptCalculated?: (result: InterceptResult | null) => void;
  onAskCopilot?: (question: string) => void;
}

export function InterceptCalculator({ alert: a, onInterceptCalculated, onAskCopilot }: Props) {
  const basesQuery = useQuery({
    queryKey: ["tactical-bases"],
    queryFn: api.tacticalBases,
    staleTime: Infinity,
  });

  const bases = basesQuery.data ?? {};
  const baseNames = Object.keys(bases);

  // Default base: Mandapam or first available
  const [base, setBase] = useState<string>("ICGS Mandapam");
  const [speed, setSpeed] = useState<number>(32);
  const [targetSpeed, setTargetSpeed] = useState<number>(() => {
    const implied = a.evidence?.implied_knots;
    return typeof implied === "number" ? implied : 12;
  });
  const [targetHdg, setTargetHdg] = useState<number>(90);
  const [lastResult, setLastResult] = useState<InterceptResult | null>(null);

  // Update default base if not set once bases load
  useEffect(() => {
    if (baseNames.length > 0 && !baseNames.includes(base)) {
      setBase(baseNames[0]);
    }
  }, [baseNames, base]);

  // Update speed when base changes to that base's default speed
  const handleBaseChange = (b: string) => {
    setBase(b);
    if (bases[b]?.default_speed_knots) {
      setSpeed(bases[b].default_speed_knots);
    }
  };

  const interceptMut = useMutation({
    mutationFn: () =>
      api.calculateIntercept({
        alert_id: a.id,
        target_lat: a.lat,
        target_lon: a.lon,
        target_speed_knots: targetSpeed,
        target_heading_deg: targetHdg,
        patrol_base: base,
        patrol_speed_knots: speed,
      }),
    onSuccess: (data) => {
      setLastResult(data);
      if (onInterceptCalculated) {
        onInterceptCalculated(data);
      }
      if (data.possible) {
        sound.interceptChime();
      } else {
        sound.alertKlaxon();
      }
    },
  });

  const baseInfo = bases[base];

  return (
    <section className="case-block tactical-intercept-block">
      <div className="tactical-header">
        <h3>⚡ Tactical Intercept Calculator</h3>
        <span className="tactical-badge">ICG Fast Response</span>
      </div>
      <p className="case-fine">
        Calculate optimal rendezvous vector, ETA, and boundary clearance for Coast Guard patrol craft.
      </p>

      <div className="tactical-grid">
        <label className="field">
          <span>Patrol Base</span>
          <select value={base} onChange={(e) => handleBaseChange(e.target.value)} disabled={interceptMut.isPending}>
            {baseNames.map((name) => (
              <option key={name} value={name}>
                {name} ({bases[name].asset})
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Patrol Speed ({speed} kn)</span>
          <input
            type="range"
            min="15"
            max="45"
            step="1"
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
            disabled={interceptMut.isPending}
          />
        </label>

        <label className="field">
          <span>Est. Target Speed ({targetSpeed} kn)</span>
          <input
            type="number"
            min="0"
            max="40"
            step="0.5"
            value={targetSpeed}
            onChange={(e) => setTargetSpeed(Number(e.target.value))}
            disabled={interceptMut.isPending}
          />
        </label>

        <label className="field">
          <span>Target Heading ({targetHdg}°)</span>
          <input
            type="number"
            min="0"
            max="359"
            step="5"
            value={targetHdg}
            onChange={(e) => setTargetHdg(Number(e.target.value))}
            disabled={interceptMut.isPending}
          />
        </label>
      </div>

      {baseInfo && (
        <p className="case-fine tactical-base-detail">
          Station: <strong>{base}</strong> ({baseInfo.lat.toFixed(3)}°N, {baseInfo.lon.toFixed(3)}°E) — {baseInfo.description}
        </p>
      )}

      <div className="tactical-actions">
        <button
          className="btn btn-primary tactical-compute-btn"
          onClick={() => interceptMut.mutate()}
          disabled={interceptMut.isPending}
        >
          {interceptMut.isPending ? "Calculating Vector..." : "🎯 Calculate Intercept Vector"}
        </button>
      </div>

      {interceptMut.isError && (
        <p className="error">{(interceptMut.error as Error).message}</p>
      )}

      {lastResult && (
        <div className={`tactical-result ${lastResult.possible ? "possible" : "impossible"}`}>
          <div className="tactical-result-top">
            <span className={`imbl-pill imbl-${lastResult.imbl_status ?? "none"}`}>
              {lastResult.imbl_status === "indian_waters" && "✅ Indian Territorial Waters"}
              {lastResult.imbl_status === "near_imbl" && "⚠️ Near Boundary (< 5 km)"}
              {lastResult.imbl_status === "crossed_imbl" && "🚨 Crosses IMBL into Sri Lanka"}
              {!lastResult.imbl_status && (lastResult.possible ? "Feasible" : "Impossible")}
            </span>
            {lastResult.time_minutes != null && (
              <span className="eta-badge">
                ETA: <strong>{lastResult.time_minutes.toFixed(1)} min</strong>
              </span>
            )}
          </div>

          {lastResult.possible && (
            <div className="tactical-metrics">
              <div className="metric">
                <span className="m-label">Intercept Bearing</span>
                <span className="m-val">{lastResult.patrol_bearing_deg?.toFixed(0)}°</span>
              </div>
              <div className="metric">
                <span className="m-label">Distance</span>
                <span className="m-val">{lastResult.distance_nm?.toFixed(1)} NM ({lastResult.distance_km?.toFixed(1)} km)</span>
              </div>
              <div className="metric">
                <span className="m-label">Rendezvous Point</span>
                <span className="m-val">
                  {lastResult.intercept_lat?.toFixed(3)}°N, {lastResult.intercept_lon?.toFixed(3)}°E
                </span>
              </div>
              <div className="metric">
                <span className="m-label">IMBL Distance</span>
                <span className="m-val">{lastResult.imbl_distance_km?.toFixed(1)} km</span>
              </div>
            </div>
          )}

          <p className="tactical-summary-text">{lastResult.tactical_summary}</p>

          {onAskCopilot && (
            <button
              className="btn btn-quiet tactical-ask-btn"
              onClick={() => onAskCopilot(`How does the intercept from ${base} compare to Thoothukudi for alert ${a.id}?`)}
            >
              Ask Copilot about alternatives
            </button>
          )}
        </div>
      )}
    </section>
  );
}
