import { useMemo, useState } from "react";

import type { LegoConnectionConfiguration } from "./fabric-client.js";
import type { FabricTranslate } from "./fabric-i18n.js";

type HubModel = LegoConnectionConfiguration["hubModel"];
type PortKind = LegoConnectionConfiguration["ports"][string];

const PORTS: Record<HubModel, string[]> = {
  "spike-prime": ["A", "B", "C", "D", "E", "F"],
  "spike-essential": ["A", "B"],
  "robot-inventor": ["A", "B", "C", "D", "E", "F"],
};

const INITIAL_PORTS: Record<string, PortKind> = {
  A: "motor",
  B: "motor",
  C: "distance",
  D: "empty",
  E: "empty",
  F: "empty",
};

export function FabricLegoSetup({
  busy,
  canConnect,
  connected,
  onConnect,
  t,
}: {
  busy: boolean;
  canConnect: boolean;
  connected: boolean;
  onConnect: (configuration: LegoConnectionConfiguration) => void;
  t: FabricTranslate;
}) {
  const [hubName, setHubName] = useState("");
  const [hubModel, setHubModel] = useState<HubModel>("spike-prime");
  const [ports, setPorts] = useState<Record<string, PortKind>>(INITIAL_PORTS);
  const visiblePorts = PORTS[hubModel];
  const configuration = useMemo<LegoConnectionConfiguration>(
    () => ({
      hubName: hubName.trim(),
      hubModel,
      ports: Object.fromEntries(
        visiblePorts.map((port) => [port, ports[port] ?? "empty"]),
      ),
    }),
    [hubModel, hubName, ports, visiblePorts],
  );
  const connectedPortCount = Object.values(configuration.ports).filter(
    (kind) => kind !== "empty",
  ).length;

  return (
    <div className="fabric-lego-setup">
      <strong>{connected ? t("lego.another") : t("lego.setup")}</strong>
      <p>{t("lego.help")}</p>
      <label>
        {t("lego.name")}
        <input
          type="text"
          value={hubName}
          maxLength={80}
          autoComplete="off"
          spellCheck={false}
          placeholder="CIT LEGO A"
          onChange={(event) => setHubName(event.target.value)}
        />
      </label>
      <label>
        {t("lego.model")}
        <select
          value={hubModel}
          onChange={(event) => setHubModel(event.target.value as HubModel)}
        >
          <option value="spike-prime">SPIKE Prime</option>
          <option value="spike-essential">SPIKE Essential</option>
          <option value="robot-inventor">MINDSTORMS Robot Inventor</option>
        </select>
      </label>
      <fieldset>
        <legend>{t("lego.ports")}</legend>
        <div className="fabric-lego-ports">
          {visiblePorts.map((port) => (
            <label key={port}>
              {t("lego.port", { port })}
              <select
                value={ports[port] ?? "empty"}
                onChange={(event) =>
                  setPorts((current) => ({
                    ...current,
                    [port]: event.target.value as PortKind,
                  }))
                }
              >
                <option value="empty">{t("lego.empty")}</option>
                <option value="motor">{t("lego.motor")}</option>
                <option value="distance">{t("lego.distance")}</option>
                <option value="color">{t("lego.color")}</option>
                <option value="force">{t("lego.force")}</option>
              </select>
            </label>
          ))}
        </div>
      </fieldset>
      <button
        className="fabric-connect-device"
        type="button"
        disabled={
          !canConnect ||
          busy ||
          configuration.hubName.length === 0 ||
          connectedPortCount === 0
        }
        onClick={() => onConnect(configuration)}
      >
        {busy ? t("lego.connecting") : t("lego.connect")}
      </button>
      <small>{t("lego.safety")}</small>
    </div>
  );
}
