import type { IntegrationNode } from "@citxr/protocol";

import type { FabricTranslate } from "./fabric-i18n.js";
import {
  wonderControlAvailability,
  wonderNodeModel,
  WONDER_HEAD_CAPABILITY,
  WONDER_LIGHT_CAPABILITY,
  WONDER_SOUND_CAPABILITY,
  WONDER_STOP_CAPABILITY,
  WONDER_VELOCITY_CAPABILITY,
} from "./fabric-wonder-workshop.js";

export interface WonderRobotAssignment {
  role: string;
  node: IntegrationNode;
}

export function FabricWonderWorkshopPanel({
  robots,
  sessionState,
  sessionArmed,
  busy,
  canSubmit,
  onCommand,
  t,
}: {
  robots: WonderRobotAssignment[];
  sessionState: string;
  sessionArmed: boolean;
  busy: boolean;
  canSubmit: boolean;
  onCommand: (
    role: string,
    action: string,
    parameters: Record<string, number>,
    label: string,
  ) => void;
  t: FabricTranslate;
}) {
  if (robots.length === 0) return null;
  return (
    <section className="fabric-panel fabric-wonder-panel">
      <div className="fabric-panel-heading">
        <div>
          <p className="eyebrow">{t("wonder.eyebrow")}</p>
          <h2>{t("wonder.title")}</h2>
        </div>
      </div>
      <p className="fabric-help">{t("wonder.help")}</p>
      <div className="fabric-wonder-grid">
        {robots.map(({ role, node }) => {
          const model = wonderNodeModel(node) ?? "dot";
          const available = wonderControlAvailability(
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
                    {model === "dash" ? t("wonder.dash") : t("wonder.dot")} ·{" "}
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
                <strong>{t("wonder.lights")}</strong>
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
                          WONDER_LIGHT_CAPABILITY,
                          {
                            red: Number(red),
                            green: Number(green),
                            blue: Number(blue),
                          },
                          t(`wonder.color.${name}` as "wonder.color.blue"),
                        )
                      }
                    >
                      {t(`wonder.color.${name}` as "wonder.color.blue")}
                    </button>
                  ))}
                </div>
              </div>

              <div className="fabric-wonder-control-group">
                <strong>{t("wonder.sounds")}</strong>
                <div className="fabric-wonder-buttons">
                  {[0, 1, 2].map((cueIndex) => (
                    <button
                      type="button"
                      key={cueIndex}
                      disabled={!physicalEnabled}
                      onClick={() =>
                        onCommand(
                          role,
                          WONDER_SOUND_CAPABILITY,
                          { cueIndex },
                          t("wonder.soundLabel", { number: cueIndex + 1 }),
                        )
                      }
                    >
                      {t("wonder.soundLabel", { number: cueIndex + 1 })}
                    </button>
                  ))}
                </div>
              </div>

              {model === "dash" && (
                <>
                  <div className="fabric-wonder-control-group">
                    <strong>{t("wonder.drive")}</strong>
                    <div className="fabric-wonder-pad">
                      <button
                        type="button"
                        disabled={!physicalEnabled}
                        onClick={() =>
                          onCommand(
                            role,
                            WONDER_VELOCITY_CAPABILITY,
                            velocity(0.12, 0),
                            t("wonder.forward"),
                          )
                        }
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        disabled={!physicalEnabled}
                        onClick={() =>
                          onCommand(
                            role,
                            WONDER_VELOCITY_CAPABILITY,
                            velocity(0, -0.35),
                            t("wonder.left"),
                          )
                        }
                      >
                        ←
                      </button>
                      <button
                        className="is-stop"
                        type="button"
                        disabled={!canSubmit || busy || !available.stop}
                        onClick={() =>
                          onCommand(
                            role,
                            WONDER_STOP_CAPABILITY,
                            {},
                            t("wonder.stop"),
                          )
                        }
                      >
                        ■
                      </button>
                      <button
                        type="button"
                        disabled={!physicalEnabled}
                        onClick={() =>
                          onCommand(
                            role,
                            WONDER_VELOCITY_CAPABILITY,
                            velocity(0, 0.35),
                            t("wonder.right"),
                          )
                        }
                      >
                        →
                      </button>
                      <button
                        type="button"
                        disabled={!physicalEnabled}
                        onClick={() =>
                          onCommand(
                            role,
                            WONDER_VELOCITY_CAPABILITY,
                            velocity(-0.1, 0),
                            t("wonder.backward"),
                          )
                        }
                      >
                        ↓
                      </button>
                    </div>
                    <small>{t("wonder.nudge")}</small>
                  </div>
                  <div className="fabric-wonder-control-group">
                    <strong>{t("wonder.head")}</strong>
                    <div className="fabric-wonder-buttons">
                      {[
                        [t("wonder.left"), -35, 0],
                        [t("wonder.center"), 0, 0],
                        [t("wonder.right"), 35, 0],
                        [t("wonder.up"), 0, -5],
                        [t("wonder.down"), 0, 10],
                      ].map(([label, panDegrees, tiltDegrees]) => (
                        <button
                          type="button"
                          key={String(label)}
                          disabled={!physicalEnabled}
                          onClick={() =>
                            onCommand(
                              role,
                              WONDER_HEAD_CAPABILITY,
                              {
                                panDegrees: Number(panDegrees),
                                tiltDegrees: Number(tiltDegrees),
                              },
                              String(label),
                            )
                          }
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}
              {!available.physical && !node.simulated && (
                <p className="fabric-wonder-lock">{t("wonder.locked")}</p>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

const velocity = (forward: number, clockwise: number) => ({
  forwardMetersPerSecond: forward,
  rightMetersPerSecond: 0,
  clockwiseRadiansPerSecond: clockwise,
});
