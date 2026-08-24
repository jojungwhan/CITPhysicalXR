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
  connectedPlugCount,
  plugs,
  sessionState,
  sessionMode,
  sessionArmed,
  busy,
  canSubmit,
  canManageSession,
  canOpenControls,
  requiredRolesReady,
  onOpenControls,
  onEnableControls,
  onPower,
  locale,
  t,
}: {
  connectedPlugCount: number;
  plugs: FabricSmartPlugAssignment[];
  sessionState: string;
  sessionMode: "simulation" | "physical" | undefined;
  sessionArmed: boolean;
  busy: boolean;
  canSubmit: boolean;
  canManageSession: boolean;
  canOpenControls: boolean;
  requiredRolesReady: boolean;
  onOpenControls: () => void;
  onEnableControls: () => void;
  onPower: (role: string, on: boolean) => void;
  locale: Locale;
  t: FabricTranslate;
}) {
  const canTurnOff = canSubmit && !busy && plugs.length > 0;
  const canTurnOn =
    canTurnOff &&
    sessionState === "active" &&
    (sessionMode !== "physical" || sessionArmed);

  return (
    <section
      className="fabric-panel fabric-smart-plug-panel"
      id="smart-plug-controls"
    >
      <div className="fabric-panel-heading">
        <p className="eyebrow">{t("plug.eyebrow")}</p>
        <h2>{t("plug.title")}</h2>
      </div>
      {plugs.length === 0 ? (
        <div className="fabric-plug-control-entry">
          <div>
            <strong>
              {t("plug.connectedReady", { count: connectedPlugCount })}
            </strong>
            <span>{t("plug.openControlsHelp")}</span>
          </div>
          <button
            type="button"
            disabled={busy || !canSubmit || !canOpenControls}
            onClick={onOpenControls}
          >
            {t("plug.openControls")}
          </button>
        </div>
      ) : (
        <>
          {!canTurnOn && (
            <div className="fabric-plug-safety-gate">
              <div>
                <strong>{t("plug.powerOnLocked")}</strong>
                <span>{t("plug.powerOnLockedHelp")}</span>
              </div>
              <button
                type="button"
                disabled={busy || !canManageSession || !requiredRolesReady}
                onClick={onEnableControls}
              >
                {t("plug.enablePowerOn")}
              </button>
            </div>
          )}
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
                    <small>
                      {canTurnOn ? t("plug.turnOnHelp") : t("plug.afterSafety")}
                    </small>
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
        </>
      )}
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
