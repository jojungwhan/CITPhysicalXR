import type { IntegrationNode } from "@citxr/protocol";

import {
  FLIGHT_EMERGENCY_STOP_CAPABILITY,
  FLIGHT_LAND_CAPABILITY,
  FLIGHT_MOVE_CAPABILITY,
  FLIGHT_ROTATE_CAPABILITY,
  FLIGHT_TAKEOFF_CAPABILITY,
  supportsManualTelloFlight,
} from "./fabric-drone.js";
import { fabricConnectionState, type FabricTranslate } from "./fabric-i18n.js";

export interface AssignedDrone {
  role: string;
  node: IntegrationNode;
}

interface FabricDronePanelProps {
  drones: AssignedDrone[];
  sessionState: string;
  sessionArmed: boolean;
  busy: boolean;
  canSubmit: boolean;
  canManageSession: boolean;
  safetyConfirmed: boolean;
  onSafetyConfirmedChange: (confirmed: boolean) => void;
  onCommand: (
    role: string,
    action: string,
    parameters: Record<string, unknown>,
    label: string,
  ) => void;
  t: FabricTranslate;
}

export function FabricDronePanel({
  drones,
  sessionState,
  sessionArmed,
  busy,
  canSubmit,
  canManageSession,
  safetyConfirmed,
  onSafetyConfirmedChange,
  onCommand,
  t,
}: FabricDronePanelProps) {
  if (drones.length === 0) return null;

  const confirmations = {
    instructorPresent: safetyConfirmed,
    flightAreaClear: safetyConfirmed,
    emergencyPlanReady: safetyConfirmed,
  };
  const manualControlsReady =
    safetyConfirmed && canSubmit && canManageSession && !busy;
  const sessionReady = sessionState === "active" && sessionArmed;

  return (
    <section className="fabric-panel fabric-drone-panel">
      <div className="fabric-panel-heading">
        <p className="eyebrow">{t("drone.eyebrow")}</p>
        <h2>{t("drone.title")}</h2>
      </div>
      <div className="fabric-drone-checklist">
        <label className="fabric-compact-confirmation">
          <input
            type="checkbox"
            checked={safetyConfirmed}
            onChange={(event) => onSafetyConfirmedChange(event.target.checked)}
          />
          {t("flight.confirmOnce")}
        </label>
        <small>
          {sessionReady
            ? t("drone.sessionReady")
            : t("drone.sessionAutoPrepare")}
        </small>
      </div>
      <div className="fabric-drone-list">
        {drones.map(({ role, node }, index) => {
          const supportsFlight = supportsManualTelloFlight(node);
          const send = (
            action: string,
            parameters: Record<string, unknown>,
            label: string,
          ) => onCommand(role, action, parameters, label);
          return (
            <article className="fabric-drone-row" key={role}>
              <div className="fabric-drone-identity">
                <strong>{node.displayName}</strong>
                <small>
                  {t("drone.role", { number: index + 1 })} ·{" "}
                  {fabricConnectionState(node, t)}
                </small>
                {!supportsFlight && <small>{t("drone.restartAdapter")}</small>}
              </div>
              <div className="fabric-drone-primary-actions">
                <button
                  className="fabric-drone-takeoff"
                  type="button"
                  disabled={!supportsFlight || !manualControlsReady}
                  onClick={() =>
                    send(
                      FLIGHT_TAKEOFF_CAPABILITY,
                      confirmations,
                      t("drone.takeoff"),
                    )
                  }
                >
                  {t("drone.takeoff")}
                </button>
                <button
                  type="button"
                  disabled={!canSubmit || busy}
                  onClick={() =>
                    send(FLIGHT_LAND_CAPABILITY, {}, t("drone.land"))
                  }
                >
                  {t("drone.land")}
                </button>
                <button
                  className="fabric-drone-emergency"
                  type="button"
                  disabled={!canSubmit || busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        t("drone.confirm", { name: node.displayName }),
                      )
                    ) {
                      send(
                        FLIGHT_EMERGENCY_STOP_CAPABILITY,
                        {},
                        t("drone.emergency"),
                      );
                    }
                  }}
                >
                  {t("drone.emergency")}
                </button>
              </div>
              <details className="fabric-drone-manual-controls">
                <summary>{t("drone.manual")}</summary>
                <div className="fabric-drone-move-grid">
                  {(
                    [
                      ["forward", "drone.forward"],
                      ["back", "drone.back"],
                      ["left", "drone.left"],
                      ["right", "drone.right"],
                      ["up", "drone.up"],
                      ["down", "drone.down"],
                    ] as const
                  ).map(([direction, labelKey]) => (
                    <button
                      type="button"
                      key={direction}
                      disabled={!supportsFlight || !manualControlsReady}
                      onClick={() =>
                        send(
                          FLIGHT_MOVE_CAPABILITY,
                          {
                            ...confirmations,
                            direction,
                            distanceCentimeters: 20,
                          },
                          t(labelKey),
                        )
                      }
                    >
                      {t(labelKey)}
                    </button>
                  ))}
                </div>
                <div className="fabric-drone-rotate-grid">
                  <button
                    type="button"
                    disabled={!supportsFlight || !manualControlsReady}
                    onClick={() =>
                      send(
                        FLIGHT_ROTATE_CAPABILITY,
                        { ...confirmations, clockwise: false, degrees: 30 },
                        t("drone.rotateCounterclockwise"),
                      )
                    }
                  >
                    {t("drone.rotateCounterclockwise")}
                  </button>
                  <button
                    type="button"
                    disabled={!supportsFlight || !manualControlsReady}
                    onClick={() =>
                      send(
                        FLIGHT_ROTATE_CAPABILITY,
                        { ...confirmations, clockwise: true, degrees: 30 },
                        t("drone.rotateClockwise"),
                      )
                    }
                  >
                    {t("drone.rotateClockwise")}
                  </button>
                </div>
              </details>
            </article>
          );
        })}
      </div>
    </section>
  );
}
