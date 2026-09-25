import { useEffect, useRef, useState } from "react";

import {
  FabricApiError,
  type FabricClient,
  type FabricPlugGateway,
} from "./fabric-client.js";
import type { FabricTranslate } from "./fabric-i18n.js";

export function FabricGatewayPlugPanel({
  gateway,
  busy,
  canSubmit,
  onPower,
  t,
}: {
  gateway: FabricPlugGateway;
  busy: boolean;
  canSubmit: boolean;
  onPower: (nodeIds: string[], on: boolean) => void;
  t: FabricTranslate;
}) {
  const available = gateway.plugs.filter((plug) => plug.available);
  const disabled =
    busy || !canSubmit || !gateway.canControl || !gateway.connected;
  return (
    <section
      className="fabric-panel fabric-gateway-plugs"
      aria-label={`${t("gateway.title")} · ${gateway.displayName}`}
    >
      <header className="fabric-panel-heading">
        <div>
          <p className="eyebrow">{t("gateway.title")}</p>
          <h2>{gateway.displayName}</h2>
        </div>
        <p role="status">
          {gateway.connected
            ? t("gateway.connected", {
                count: available.length,
                total: gateway.plugs.length,
              })
            : t("gateway.offline")}
        </p>
      </header>
      {!gateway.connected && <p>{t("gateway.offlineHelp")}</p>}
      <div className="fabric-plug-group-controls">
        <span>{t("gateway.group")}</span>
        <div className="fabric-plug-group-actions">
          <button
            type="button"
            className="fabric-plug-group-on"
            disabled={
              disabled ||
              available.length === 0 ||
              available.length !== gateway.plugs.length
            }
            onClick={() =>
              onPower(
                gateway.plugs.map((plug) => plug.nodeId),
                true,
              )
            }
          >
            {t("plug.turnOnAll")}
          </button>
          <button
            type="button"
            className="fabric-plug-group-off"
            disabled={disabled || available.length === 0}
            onClick={() =>
              onPower(
                gateway.plugs.map((plug) => plug.nodeId),
                false,
              )
            }
          >
            {t("plug.turnOffAll")}
          </button>
        </div>
      </div>
      <ul className="fabric-smart-plug-list">
        {gateway.plugs.map((plug, index) => {
          const known =
            gateway.connected && plug.available && typeof plug.on === "boolean";
          return (
            <li
              key={plug.nodeId}
              className={`fabric-plug-row fabric-gateway-plug-row${plug.available && gateway.connected ? "" : " is-unavailable"}`}
            >
              <div className="fabric-plug-identity">
                <span className="fabric-plug-name">
                  {t("gateway.plug", { number: index + 1 })}
                </span>
                <small>{plug.displayName}</small>
              </div>
              <span
                className={`fabric-plug-state ${known ? (plug.on ? "is-on" : "is-off") : "is-unknown"}`}
              >
                {known
                  ? t(plug.on ? "plug.onState" : "plug.offState")
                  : t("gateway.stateUnknown")}
              </span>
              <div className="fabric-plug-remote-actions">
                <button
                  type="button"
                  className="fabric-plug-remote-on"
                  disabled={disabled || !plug.available}
                  aria-label={`${t("gateway.plug", { number: index + 1 })} ${t("plug.turnOn")}`}
                  onClick={() => onPower([plug.nodeId], true)}
                >
                  {t("plug.turnOn")}
                </button>
                <button
                  type="button"
                  className="fabric-plug-remote-off"
                  disabled={disabled || !plug.available}
                  aria-label={`${t("gateway.plug", { number: index + 1 })} ${t("plug.turnOff")}`}
                  onClick={() => onPower([plug.nodeId], false)}
                >
                  {t("plug.turnOff")}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function FabricGatewayPlugs({
  client,
  canSubmit,
  t,
}: {
  client: FabricClient;
  canSubmit: boolean;
  t: FabricTranslate;
}) {
  const [gateways, setGateways] = useState<FabricPlugGateway[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const actionPending = useRef(false);
  const generation = useRef(0);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      const requestGeneration = generation.current;
      try {
        if (!actionPending.current) {
          const next = await client.listPlugGateways();
          if (active && generation.current === requestGeneration)
            setGateways(next);
        }
      } catch (error) {
        if (active && generation.current === requestGeneration) {
          if (
            error instanceof FabricApiError &&
            (error.status === 404 || error.status === 403)
          )
            setGateways([]);
          else
            setGateways((current) =>
              current.map((gateway) => ({
                ...gateway,
                connected: false,
                plugs: gateway.plugs.map((plug) => ({
                  ...plug,
                  available: false,
                  on: null,
                })),
              })),
            );
        }
      } finally {
        if (active) timer = setTimeout(() => void refresh(), 5000);
      }
    };
    void refresh();
    return () => {
      active = false;
      mounted.current = false;
      clearTimeout(timer);
    };
  }, [client]);

  async function power(siteId: string, nodeIds: string[], on: boolean) {
    if (actionPending.current) return;
    actionPending.current = true;
    generation.current += 1;
    setBusy(true);
    setMessage(null);
    try {
      const result = await client.setGatewayPlugPower(siteId, nodeIds, on);
      if (mounted.current)
        setMessage(t(result.accepted ? "gateway.accepted" : "gateway.partial"));
    } catch {
      if (mounted.current) setMessage(t("gateway.unknownResult"));
    } finally {
      try {
        const next = await client.listPlugGateways();
        if (mounted.current) setGateways(next);
      } catch {
        if (mounted.current)
          setGateways((current) =>
            current.map((gateway) =>
              gateway.siteId === siteId
                ? { ...gateway, connected: false }
                : gateway,
            ),
          );
      }
      actionPending.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <>
      {message !== null && (
        <p className="fabric-notice" role="status">
          {message}
        </p>
      )}
      {gateways.map((gateway) => (
        <FabricGatewayPlugPanel
          key={gateway.siteId}
          gateway={gateway}
          busy={busy}
          canSubmit={canSubmit}
          onPower={(nodeIds, on) => void power(gateway.siteId, nodeIds, on)}
          t={t}
        />
      ))}
    </>
  );
}
