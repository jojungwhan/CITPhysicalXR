import type { IntegrationNode } from "@citxr/protocol";

import type { FabricTranslate } from "./fabric-i18n.js";
import {
  spheroControlAvailability,
  spheroNudgeVelocity,
  SPHERO_AIM_CAPABILITY,
  SPHERO_LIGHT_CAPABILITY,
  SPHERO_STOP_CAPABILITY,
  SPHERO_VELOCITY_CAPABILITY,
  type SpheroVariant,
} from "./fabric-sphero-bolt.js";

export interface SpheroAssignment {
  role: string;
  node: IntegrationNode;
}

export function FabricSpheroPanel({
  robots,
  variant = "bolt",
  sessionState,
  sessionArmed,
  busy,
  canSubmit,
  canManageSession,
  onCommand,
  t,
}: {
  robots: SpheroAssignment[];
  variant?: SpheroVariant;
  sessionState: string;
  sessionArmed: boolean;
  busy: boolean;
  canSubmit: boolean;
  canManageSession: boolean;
  onCommand: (
    role: string,
    action: string,
    parameters: Record<string, number>,
    label: string,
  ) => void;
  t: FabricTranslate;
}) {
  if (robots.length === 0) return null;
  const canPrepareSession =
    canManageSession &&
    ["", "ready", "paused", "active"].includes(sessionState);
  const prefix = variant === "ollie" ? "ollie" : "sphero";

  return (
    <section className="fabric-panel fabric-sphero-panel" id="sphero-controls">
      <div className="fabric-panel-heading">
        <div>
          <p className="eyebrow">{t("sphero.eyebrow")}</p>
          <h2>{t(`${prefix}.title` as "sphero.title")}</h2>
        </div>
      </div>
      <p className="fabric-help">{t(`${prefix}.help` as "sphero.help")}</p>
      <div className="fabric-wonder-grid">
        {robots.map(({ role, node }) => {
          const available = spheroControlAvailability(
            node,
            sessionState,
            sessionArmed,
          );
          const physicalEnabled =
            canSubmit && !busy && (available.physical || canPrepareSession);
          const lightEnabled =
            canSubmit && !busy && (available.light || canPrepareSession);
          return (
            <article className="fabric-wonder-card" key={node.nodeId}>
              <header>
                <div>
                  <strong>{node.displayName}</strong>
                  <small>
                    {t(`${prefix}.capabilities` as "sphero.capabilities")} ·{" "}
                    {role}
                  </small>
                </div>
                <span
                  className={node.simulated ? "is-simulation" : "is-physical"}
                >
                  {node.simulated ? t("nodes.simulator") : t("nodes.physical")}
                </span>
              </header>

              <div className="fabric-wonder-control-group">
                <strong>{t(`${prefix}.aimTitle` as "sphero.aimTitle")}</strong>
                <p>{t(`${prefix}.aimHelp` as "sphero.aimHelp")}</p>
                <button
                  type="button"
                  disabled={!physicalEnabled}
                  onClick={() =>
                    onCommand(
                      role,
                      SPHERO_AIM_CAPABILITY,
                      {},
                      t(`${prefix}.aimButton` as "sphero.aimButton"),
                    )
                  }
                >
                  {t(`${prefix}.aimButton` as "sphero.aimButton")}
                </button>
              </div>

              <div className="fabric-wonder-control-group">
                <strong>{t(`${prefix}.drive` as "sphero.drive")}</strong>
                <div className="fabric-wonder-pad">
                  <button
                    type="button"
                    disabled={!physicalEnabled}
                    aria-label={t("sphero.forward")}
                    onClick={() =>
                      onCommand(
                        role,
                        SPHERO_VELOCITY_CAPABILITY,
                        spheroNudgeVelocity(1, 0, variant),
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
                        spheroNudgeVelocity(0, -1, variant),
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
                        spheroNudgeVelocity(0, 1, variant),
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
                        spheroNudgeVelocity(-1, 0, variant),
                        t("sphero.backward"),
                      )
                    }
                  >
                    ↓
                  </button>
                </div>
                <small>{t(`${prefix}.nudge` as "sphero.nudge")}</small>
              </div>

              <div className="fabric-wonder-control-group">
                <strong>{t(`${prefix}.lights` as "sphero.lights")}</strong>
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
            </article>
          );
        })}
      </div>
    </section>
  );
}
