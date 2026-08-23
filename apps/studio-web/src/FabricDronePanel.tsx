import type { IntegrationNode } from "@citxr/protocol";

import { fabricConnectionState, type FabricTranslate } from "./fabric-i18n.js";

export interface AssignedDrone {
  role: string;
  node: IntegrationNode;
}

interface FabricDronePanelProps {
  drones: AssignedDrone[];
  busy: boolean;
  canSubmit: boolean;
  onLand: (role: string) => void;
  onEmergencyStop: (role: string) => void;
  t: FabricTranslate;
}

export function FabricDronePanel({
  drones,
  busy,
  canSubmit,
  onLand,
  onEmergencyStop,
  t,
}: FabricDronePanelProps) {
  if (drones.length === 0) return null;
  return (
    <section className="fabric-panel fabric-drone-panel">
      <div className="fabric-panel-heading">
        <p className="eyebrow">{t("drone.eyebrow")}</p>
        <h2>{t("drone.title")}</h2>
      </div>
      <p className="fabric-help">{t("drone.help")}</p>
      <div className="fabric-drone-list">
        {drones.map(({ role, node }, index) => (
          <article className="fabric-drone-row" key={role}>
            <div>
              <strong>{node.displayName}</strong>
              <small>
                {t("drone.role", { number: index + 1 })} ·{" "}
                {fabricConnectionState(node, t)}
              </small>
            </div>
            <div className="fabric-drone-actions">
              <button
                type="button"
                disabled={!canSubmit || busy}
                onClick={() => onLand(role)}
              >
                {t("drone.land")}
                <small>{t("drone.landHelp")}</small>
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
                    onEmergencyStop(role);
                  }
                }}
              >
                {t("drone.emergency")}
                <small>{t("drone.emergencyHelp")}</small>
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
