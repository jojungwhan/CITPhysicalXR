import type { IntegrationNode } from "@citxr/protocol";

import {
  fabricFormatTime,
  fabricRoleText,
  type FabricTranslate,
} from "./fabric-i18n.js";
import type { SmartPlugState } from "./fabric-smart-plug.js";
import type { Locale } from "./i18n.js";

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
  locale,
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
  locale: Locale;
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
        {plugs.map(({ role, node, state }) => (
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
              <div>
                <strong>{fabricRoleText(role, t).name}</strong>
                <small>
                  {node.displayName} · {node.nodeId}
                </small>
                <small>
                  {metadataText(node, "vendorBrand") ?? "Matter"} ·{" "}
                  {metadataText(node, "model") ?? "smart plug"}
                </small>
                <small>
                  {state === undefined
                    ? t("plug.stateUnknown")
                    : t("plug.observed", {
                        time: fabricFormatTime(state.observedAt, locale),
                        source:
                          state.source === undefined
                            ? ""
                            : ` · ${state.source}`,
                      })}
                </small>
              </div>
            </div>
            <div className="fabric-smart-plug-actions">
              <button
                className="fabric-power-on"
                type="button"
                disabled={!canTurnOn}
                onClick={() => onPower(role, true)}
              >
                {t("plug.turnOn")}
                <small>{t("plug.turnOnHelp")}</small>
              </button>
              <button
                className="fabric-power-off"
                type="button"
                disabled={!canTurnOff}
                onClick={() => onPower(role, false)}
              >
                {t("plug.turnOff")}
                <small>{t("plug.turnOffHelp")}</small>
              </button>
            </div>
          </div>
        ))}
      </div>
      <p className="fabric-help">{t("plug.help")}</p>
    </section>
  );
}

const metadataText = (
  node: IntegrationNode,
  key: string,
): string | undefined => {
  const value = node.metadata?.[key];
  return typeof value === "string" && value.trim() !== ""
    ? value.trim()
    : undefined;
};
