import type { IntegrationNode } from "@citxr/protocol";

import type { FabricTranslate } from "./fabric-i18n.js";
import {
  spheroControlAvailability,
  spheroNudgeVelocity,
  SPHERO_AIM_CAPABILITY,
  SPHERO_LIGHT_CAPABILITY,
  SPHERO_STOP_CAPABILITY,
  SPHERO_VELOCITY_CAPABILITY,
} from "./fabric-sphero-bolt.js";

export interface SpheroAssignment {
  role: string;
  node: IntegrationNode;
}

export function FabricSpheroPanel({
  robots,
  connectedRobotCount,
  sessionState,
  sessionArmed,
  busy,
  canSubmit,
  canManageSession,
  canOpenControls,
  safetyConfirmed,
  onSafetyConfirmedChange,
  onOpenControls,
  onEnableControls,
  onCommand,
  t,
}: {
  robots: SpheroAssignment[];
  connectedRobotCount: number;
  sessionState: string;
  sessionArmed: boolean;
  busy: boolean;
  canSubmit: boolean;
  canManageSession: boolean;
  canOpenControls: boolean;
  safetyConfirmed: boolean;
  onSafetyConfirmedChange: (confirmed: boolean) => void;
  onOpenControls: () => void;
  onEnableControls: () => void;
  onCommand: (
    role: string,
    action: string,
    parameters: Record<string, number>,
    label: string,
  ) => void;
  t: FabricTranslate;
}) {
  const physicalSafetyRequired =
    !sessionArmed && robots.some(({ node }) => !node.simulated);
  const movementLocked =
    robots.length > 0 &&
    robots.some(
      ({ node }) =>
        !spheroControlAvailability(node, sessionState, sessionArmed).physical,
    );
  const canEnableControls =
    canManageSession &&
    canSubmit &&
    !busy &&
    ["ready", "paused", "active"].includes(sessionState) &&
    (!physicalSafetyRequired || safetyConfirmed);

  return (
    <section className="fabric-panel fabric-sphero-panel" id="sphero-controls">
      <div className="fabric-panel-heading">
        <div>
          <p className="eyebrow">{t("sphero.eyebrow")}</p>
          <h2>{t("sphero.title")}</h2>
        </div>
      </div>
      <p className="fabric-help">{t("sphero.help")}</p>
      {robots.length === 0 ? (
        <div className="fabric-sphero-control-entry">
          <div>
            <strong>
              {t("sphero.connectedReady", { count: connectedRobotCount })}
            </strong>
            <span>{t("sphero.openControlsHelp")}</span>
          </div>
          <button
            type="button"
            disabled={busy || !canSubmit || !canOpenControls}
            onClick={onOpenControls}
          >
            {t("sphero.openControls")}
          </button>
        </div>
      ) : (
        <>
          {movementLocked && (
            <div className="fabric-sphero-safety-gate">
              <div>
                <strong>{t("sphero.movementLocked")}</strong>
                <span>{t("sphero.movementLockedHelp")}</span>
                {physicalSafetyRequired && (
                  <label>
                    <input
                      type="checkbox"
                      checked={safetyConfirmed}
                      onChange={(event) =>
                        onSafetyConfirmedChange(event.target.checked)
                      }
                    />
                    <span>{t("safety.confirm")}</span>
                  </label>
                )}
              </div>
              <button
                type="button"
                disabled={!canEnableControls}
                onClick={onEnableControls}
              >
                {sessionState === "active"
                  ? t("sphero.pauseEnableMovement")
                  : t("sphero.enableMovement")}
              </button>
            </div>
          )}
          <div className="fabric-wonder-grid">
            {robots.map(({ role, node }) => {
              const available = spheroControlAvailability(
                node,
                sessionState,
                sessionArmed,
              );
              const physicalEnabled = canSubmit && !busy && available.physical;
              const lightEnabled = canSubmit && !busy && available.light;
              return (
                <article className="fabric-wonder-card" key={node.nodeId}>
                  <header>
                    <div>
                      <strong>{node.displayName}</strong>
                      <small>
                        {t("sphero.boltCapabilities")} · {role}
                      </small>
                    </div>
                    <span
                      className={
                        node.simulated ? "is-simulation" : "is-physical"
                      }
                    >
                      {node.simulated
                        ? t("nodes.simulator")
                        : t("nodes.physical")}
                    </span>
                  </header>

                  <div className="fabric-wonder-control-group">
                    <strong>{t("sphero.aimTitle")}</strong>
                    <p>{t("sphero.aimHelp")}</p>
                    <button
                      type="button"
                      disabled={!physicalEnabled}
                      onClick={() =>
                        onCommand(
                          role,
                          SPHERO_AIM_CAPABILITY,
                          {},
                          t("sphero.aimButton"),
                        )
                      }
                    >
                      {t("sphero.aimButton")}
                    </button>
                  </div>

                  <div className="fabric-wonder-control-group">
                    <strong>{t("sphero.drive")}</strong>
                    <div className="fabric-wonder-pad">
                      <button
                        type="button"
                        disabled={!physicalEnabled}
                        aria-label={t("sphero.forward")}
                        onClick={() =>
                          onCommand(
                            role,
                            SPHERO_VELOCITY_CAPABILITY,
                            spheroNudgeVelocity(1, 0),
                            t("sphero.forward"),
                          )
                        }
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        disabled={!physicalEnabled}
                        aria-label={t("sphero.left")}
                        onClick={() =>
                          onCommand(
                            role,
                            SPHERO_VELOCITY_CAPABILITY,
                            spheroNudgeVelocity(0, -1),
                            t("sphero.left"),
                          )
                        }
                      >
                        ←
                      </button>
                      <button
                        className="is-stop"
                        type="button"
                        disabled={!canSubmit || busy || !available.stop}
                        aria-label={t("sphero.stop")}
                        onClick={() =>
                          onCommand(
                            role,
                            SPHERO_STOP_CAPABILITY,
                            {},
                            t("sphero.stop"),
                          )
                        }
                      >
                        ■
                      </button>
                      <button
                        type="button"
                        disabled={!physicalEnabled}
                        aria-label={t("sphero.right")}
                        onClick={() =>
                          onCommand(
                            role,
                            SPHERO_VELOCITY_CAPABILITY,
                            spheroNudgeVelocity(0, 1),
                            t("sphero.right"),
                          )
                        }
                      >
                        →
                      </button>
                      <button
                        type="button"
                        disabled={!physicalEnabled}
                        aria-label={t("sphero.backward")}
                        onClick={() =>
                          onCommand(
                            role,
                            SPHERO_VELOCITY_CAPABILITY,
                            spheroNudgeVelocity(-1, 0),
                            t("sphero.backward"),
                          )
                        }
                      >
                        ↓
                      </button>
                    </div>
                    <small>{t("sphero.nudge")}</small>
                  </div>

                  <div className="fabric-wonder-control-group">
                    <strong>{t("sphero.lights")}</strong>
                    <div className="fabric-wonder-buttons">
                      {[
                        ["blue", 32, 96, 255],
                        ["orange", 255, 96, 0],
                        ["green", 0, 180, 80],
                        ["off", 0, 0, 0],
                      ].map(([name, red, green, blue]) => (
                        <button
                          key={name}
                          type="button"
                          disabled={!lightEnabled}
                          onClick={() =>
                            onCommand(
                              role,
                              SPHERO_LIGHT_CAPABILITY,
                              {
                                red: Number(red),
                                green: Number(green),
                                blue: Number(blue),
                              },
                              t(`sphero.color.${name}` as "sphero.color.blue"),
                            )
                          }
                        >
                          {t(`sphero.color.${name}` as "sphero.color.blue")}
                        </button>
                      ))}
                    </div>
                  </div>
                  {!available.physical && !node.simulated && (
                    <p className="fabric-wonder-lock">{t("sphero.locked")}</p>
                  )}
                </article>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}
