import { useEffect, useState } from "react";

import type { IntegrationNode } from "@citxr/protocol";

import { fabricRoleText, type FabricTranslate } from "./fabric-i18n.js";
import type { SmartPlugState } from "./fabric-smart-plug.js";

export interface FabricSmartPlugAssignment {
  role: string;
  node: IntegrationNode;
  state: SmartPlugState | undefined;
}

const UNKNOWN_STATE_MARK = "--";

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
  const [pendingRole, setPendingRole] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (!busy) setPendingRole(undefined);
  }, [busy]);

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

  if (plugs.length === 0) return null;

  return (
    <section
      className="fabric-smart-plug-panel"
      id="smart-plug-controls"
      aria-label={t("plug.title")}
    >
      <ul className="fabric-smart-plug-list">
        {plugs.map(({ role, node, state }) => {
          const turnOn = state?.on === false;
          const action = t(turnOn ? "plug.turnOn" : "plug.turnOff");
          const name = fabricRoleText(role, t).name;
          const pending = busy && pendingRole === role;
          const tone =
            state === undefined ? "is-unknown" : state.on ? "is-on" : "is-off";
          return (
            <li
              className="fabric-plug-row"
              key={`${role}:${node.nodeId}`}
              {...(pending ? { "aria-busy": true } : {})}
            >
              <span className="fabric-plug-name">{name}</span>
              <span
                className={`fabric-plug-state ${tone}`}
                {...(state === undefined
                  ? { title: t("plug.stateUnknown") }
                  : {})}
              >
                {state === undefined
                  ? UNKNOWN_STATE_MARK
                  : t(state.on ? "plug.onState" : "plug.offState")}
              </span>
              <button
                className={`fabric-power-toggle ${turnOn ? "fabric-power-on" : "fabric-power-off"}${pending ? " is-pending" : ""}`}
                type="button"
                aria-label={`${name}: ${action}`}
                disabled={turnOn ? !canTurnOn : !canTurnOff}
                onClick={() => {
                  setPendingRole(role);
                  onPower(role, turnOn);
                }}
              >
                {action}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
