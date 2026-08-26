import type { IntegrationNode } from "@citxr/protocol";

import { fabricRoleText, type FabricTranslate } from "./fabric-i18n.js";
import type { SmartPlugState } from "./fabric-smart-plug.js";

export interface FabricSmartPlugAssignment {
  role: string;
  node: IntegrationNode;
  state: SmartPlugState | undefined;
}

export function FabricSmartPlugPanel({
  plugs,
  sessionState,
  sessionMode,
  sessionArmed,
  busy,
  canSubmit,
  canManageSession,
  requiredRolesReady,
  onPower,
  t,
}: {
  plugs: FabricSmartPlugAssignment[];
  sessionState: string;
  sessionMode: "simulation" | "physical" | undefined;
  sessionArmed: boolean;
  busy: boolean;
  canSubmit: boolean;
  canManageSession: boolean;
  requiredRolesReady: boolean;
  onPower: (role: string, on: boolean) => void;
  t: FabricTranslate;
}) {
  if (plugs.length === 0) return null;
  const canUseOrPrepareSession = sessionState !== "" || canManageSession;
  const canTurnOff =
    canSubmit &&
    !busy &&
    plugs.length > 0 &&
    requiredRolesReady &&
    canUseOrPrepareSession;
  const controlsAlreadyReady =
    sessionState === "active" && (sessionMode !== "physical" || sessionArmed);
  const canTurnOn = canTurnOff && (controlsAlreadyReady || canManageSession);

  return (
    <section
      className="fabric-panel fabric-smart-plug-panel"
      id="smart-plug-controls"
    >
      <div className="fabric-panel-heading">
        <p className="eyebrow">{t("plug.eyebrow")}</p>
        <h2>{t("plug.title")}</h2>
      </div>
      <div className="fabric-smart-plug-list">
        {plugs.map(({ role, node, state }) => {
          const turnOn = state?.on === false;
          const actionKey = turnOn ? "plug.turnOn" : "plug.turnOff";
          return (
            <div
              className="fabric-smart-plug-layout"
              key={`${role}:${node.nodeId}`}
            >
              <div className="fabric-smart-plug-state">
                <span
                  className={`fabric-plug-indicator ${state?.on ? "is-on" : "is-off"}`}
                  aria-hidden="true"
                >
                  {state === undefined
                    ? t("plug.unknownState")
                    : state.on
                      ? t("plug.onState")
                      : t("plug.offState")}
                </span>
                <strong>{fabricRoleText(role, t).name}</strong>
              </div>
              <div className="fabric-smart-plug-actions">
                <button
                  className={`fabric-power-toggle ${turnOn ? "fabric-power-on" : "fabric-power-off"}`}
                  type="button"
                  aria-label={`${fabricRoleText(role, t).name}: ${t("plug.title")}`}
                  aria-pressed={state?.on === true}
                  disabled={turnOn ? !canTurnOn : !canTurnOff}
                  onClick={() => onPower(role, turnOn)}
                >
                  {t(actionKey)}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
