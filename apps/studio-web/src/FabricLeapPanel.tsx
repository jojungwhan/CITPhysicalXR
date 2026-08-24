import type { IntegrationNode } from "@citxr/protocol";
import { useEffect, useMemo, useState } from "react";

import type { FabricClient } from "./fabric-client.js";
import {
  latestLeapTracking,
  leapHandGeometry,
  type LeapTrackingReading,
} from "./fabric-leap.js";
import { fabricFormatTime, type FabricTranslate } from "./fabric-i18n.js";
import type { Locale } from "./i18n.js";

export function FabricLeapPanel({
  client,
  sessionId,
  nodes,
  locale,
  t,
}: {
  client: FabricClient;
  sessionId: string | undefined;
  nodes: IntegrationNode[];
  locale: Locale;
  t: FabricTranslate;
}) {
  const [reading, setReading] = useState<LeapTrackingReading>();
  const [now, setNow] = useState(Date.now());
  const [pollError, setPollError] = useState(false);
  const nodeKey = useMemo(
    () =>
      nodes
        .map((node) => node.nodeId)
        .sort()
        .join("|"),
    [nodes],
  );

  useEffect(() => {
    setReading(undefined);
    setPollError(false);
    if (sessionId === undefined || nodeKey.length === 0) return;
    const allowedNodeIds = new Set(nodeKey.split("|"));
    let active = true;
    let timer: number | undefined;
    let cursor = 0;
    const poll = async () => {
      try {
        const batch = await client.listEvents(sessionId, cursor);
        if (!active) return;
        for (const stored of batch)
          cursor = Math.max(cursor, stored.streamSequence);
        const next = latestLeapTracking(batch, allowedNodeIds);
        if (next !== undefined) setReading(next);
        setPollError(false);
      } catch {
        if (active) setPollError(true);
      } finally {
        if (active) {
          setNow(Date.now());
          timer = window.setTimeout(() => void poll(), 200);
        }
      }
    };
    void poll();
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [client, nodeKey, sessionId]);

  const ageMilliseconds =
    reading === undefined
      ? Number.POSITIVE_INFINITY
      : now - Date.parse(reading.observedAt);
  const live = ageMilliseconds <= 1_500 && !pollError;
  const tracking =
    live && reading?.tracking === true && reading.hand !== undefined;
  const hand = tracking ? reading.hand : undefined;
  const geometry = hand === undefined ? undefined : leapHandGeometry(hand);
  const sourceName =
    nodes.find((node) => node.nodeId === reading?.sourceNodeId)?.displayName ??
    nodes[0]?.displayName ??
    "Leap Motion";
  const handLabel =
    hand?.handedness === "left" ? t("leap.leftHand") : t("leap.rightHand");

  return (
    <section className="fabric-panel fabric-leap-panel">
      <header className="fabric-leap-heading">
        <div>
          <span className="eyebrow">{t("leap.eyebrow")}</span>
          <h2>{t("leap.title")}</h2>
          <p>{t("leap.intro")}</p>
        </div>
        <span
          className={`fabric-media-state ${tracking ? "is-online" : "is-waiting"}`}
        >
          {tracking
            ? t("leap.handDetected")
            : live
              ? t("leap.waitingHand")
              : t("leap.waitingSignal")}
        </span>
      </header>

      <div className="fabric-leap-layout">
        <div className="fabric-leap-stage">
          <svg
            viewBox="0 0 100 100"
            role="img"
            aria-label={
              tracking
                ? t("leap.visualAltDetected", { hand: handLabel })
                : t("leap.visualAltWaiting")
            }
          >
            <defs>
              <linearGradient id="leap-stage-glow" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#60a5fa" stopOpacity="0.34" />
                <stop offset="1" stopColor="#34d399" stopOpacity="0.08" />
              </linearGradient>
            </defs>
            <rect
              x="1"
              y="1"
              width="98"
              height="98"
              rx="10"
              className="leap-stage-bg"
            />
            {[20, 40, 60, 80].map((position) => (
              <g key={position} className="leap-grid-line">
                <line x1={position} y1="6" x2={position} y2="94" />
                <line x1="6" y1={position} x2="94" y2={position} />
              </g>
            ))}
            <line x1="50" y1="8" x2="50" y2="92" className="leap-axis" />
            <line x1="8" y1="50" x2="92" y2="50" className="leap-axis" />
            <rect
              x="38"
              y="84"
              width="24"
              height="8"
              rx="4"
              className="leap-sensor"
            />
            {geometry !== undefined && hand !== undefined ? (
              <g
                className={`leap-hand is-${hand.handedness}`}
                transform={`translate(${geometry.xPercent} ${geometry.yPercent}) rotate(${geometry.rotationDegrees})`}
              >
                <line x1="0" y1="16" x2="0" y2="7" className="leap-arm" />
                <ellipse
                  cx="0"
                  cy="0"
                  rx="6.2"
                  ry="7.5"
                  className="leap-palm"
                />
                {[-28, -14, 0, 14, 28].map((angle, index) => {
                  const radians = (angle * Math.PI) / 180;
                  const length =
                    (index === 0 ? 10 : 14) * geometry.fingerExtension;
                  const spread = index === 0 ? geometry.pinchGap : 1;
                  return (
                    <line
                      key={angle}
                      x1={(Math.sin(radians) * 4.5 * spread).toFixed(2)}
                      y1={(-Math.cos(radians) * 4.5).toFixed(2)}
                      x2={(Math.sin(radians) * length * spread).toFixed(2)}
                      y2={(-Math.cos(radians) * length).toFixed(2)}
                      className="leap-finger"
                    />
                  );
                })}
                <circle cx="0" cy="0" r="1.6" className="leap-palm-center" />
              </g>
            ) : (
              <g className="leap-search-pulse">
                <circle cx="50" cy="48" r="9" />
                <circle cx="50" cy="48" r="18" />
              </g>
            )}
          </svg>
          <div className="fabric-leap-axis-labels" aria-hidden="true">
            <span>{t("leap.left")}</span>
            <span>{t("leap.forward")}</span>
            <span>{t("leap.right")}</span>
          </div>
        </div>

        <div className="fabric-leap-readout" aria-live="polite">
          <div className="fabric-leap-primary">
            <strong>{sourceName}</strong>
            <span>{reading?.state ?? t("leap.noState")}</span>
          </div>
          <p>{reading?.reason ?? t("leap.placeHand")}</p>
          <div className="fabric-leap-metrics">
            <LeapMetric
              label={t("leap.hand")}
              value={hand === undefined ? "—" : `${handLabel} #${hand.handId}`}
            />
            <LeapMetric
              label={t("leap.pinch")}
              value={
                hand === undefined
                  ? "—"
                  : `${Math.round(hand.pinchStrength * 100)}%`
              }
            />
            <LeapMetric
              label={t("leap.grab")}
              value={
                hand === undefined
                  ? "—"
                  : `${Math.round(hand.grabStrength * 100)}%`
              }
            />
            <LeapMetric
              label={t("leap.palm")}
              value={
                hand === undefined
                  ? "—"
                  : `${Math.round(hand.palmMillimeters.x)}, ${Math.round(hand.palmMillimeters.y)}, ${Math.round(hand.palmMillimeters.z)} mm`
              }
            />
            <LeapMetric
              label={t("leap.output")}
              value={
                reading === undefined
                  ? "—"
                  : `${reading.command.forwardMetersPerSecond.toFixed(2)} / ${reading.command.rightMetersPerSecond.toFixed(2)} m/s`
              }
            />
            <LeapMetric
              label={t("leap.frameRate")}
              value={
                reading?.sensorFrameRateHertz === undefined
                  ? "—"
                  : `${Math.round(reading.sensorFrameRateHertz)} Hz`
              }
            />
          </div>
          <small>
            {reading === undefined
              ? sessionId === undefined
                ? t("leap.selectLesson")
                : t("leap.noReading")
              : t("leap.updated", {
                  time: fabricFormatTime(reading.observedAt, locale),
                })}
          </small>
        </div>
      </div>
      <p className="fabric-privacy-note">{t("leap.privacy")}</p>
    </section>
  );
}

function LeapMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
