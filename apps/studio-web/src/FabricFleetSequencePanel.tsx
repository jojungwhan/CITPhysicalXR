import type { IntegrationNode } from "@citxr/protocol";
import { useEffect, useMemo, useState } from "react";

import type {
  FleetSequenceSettings,
  FleetSequenceStatus,
} from "./fabric-fleet-sequence.js";
import { fabricPhase, type FabricTranslate } from "./fabric-i18n.js";
import type { Locale } from "./i18n.js";

interface FabricFleetSequencePanelProps {
  controllerName: string;
  simulated: boolean;
  status?: FleetSequenceStatus;
  inputNodes: IntegrationNode[];
  sessionState: string;
  sessionArmed: boolean;
  busy: boolean;
  canSubmit: boolean;
  canManageSession: boolean;
  safetyConfirmed: boolean;
  onSafetyConfirmedChange: (confirmed: boolean) => void;
  onArm: (settings: FleetSequenceSettings) => void;
  onLaunch: (settings: FleetSequenceSettings) => void;
  onStart: () => void;
  onStop: () => void;
  locale: Locale;
  t: FabricTranslate;
}

export function FabricFleetSequencePanel({
  controllerName,
  simulated,
  status,
  inputNodes,
  sessionState,
  sessionArmed,
  busy,
  canSubmit,
  canManageSession,
  safetyConfirmed,
  onSafetyConfirmedChange,
  onArm,
  onLaunch,
  onStart,
  onStop,
  locale,
  t,
}: FabricFleetSequencePanelProps) {
  const availableDrones = useMemo(
    () => status?.availableDrones ?? [],
    [status?.availableDrones],
  );
  const availableDroneKey = availableDrones
    .map((drone) => drone.id)
    .join("\u0000");
  const inputKey = inputNodes.map((node) => node.nodeId).join("\u0000");
  const [droneOrder, setDroneOrder] = useState<string[]>(() =>
    availableDrones.map((drone) => drone.id),
  );
  const [allowedSources, setAllowedSources] = useState<string[]>(() =>
    inputNodes.map((node) => node.nodeId),
  );
  const [launchIntervalSeconds, setLaunchIntervalSeconds] = useState(2);
  const [minimumBatteryPercent, setMinimumBatteryPercent] = useState(30);
  useEffect(() => {
    const available = new Set(availableDrones.map((drone) => drone.id));
    setDroneOrder((current) => [
      ...current.filter((id) => available.has(id)),
      ...availableDrones
        .map((drone) => drone.id)
        .filter((id) => !current.includes(id)),
    ]);
  }, [availableDroneKey]);

  useEffect(() => {
    const available = new Set(inputNodes.map((node) => node.nodeId));
    setAllowedSources((current) => [
      ...current.filter((id) => available.has(id)),
      ...inputNodes
        .map((node) => node.nodeId)
        .filter((id) => !current.includes(id)),
    ]);
  }, [inputKey]);

  const selectedDrones = droneOrder.flatMap((id) => {
    const drone = availableDrones.find((candidate) => candidate.id === id);
    return drone === undefined ? [] : [drone];
  });
  const aircraftReady =
    selectedDrones.length >= 1 &&
    selectedDrones.every(
      (drone) =>
        drone.connection === "connected" &&
        drone.flight === "landed" &&
        drone.batteryPercent !== undefined &&
        drone.batteryPercent >= minimumBatteryPercent,
    );
  const safetyReady = simulated || safetyConfirmed;
  const sessionReady = sessionState === "active" && (simulated || sessionArmed);
  const sessionCanBePrepared = ["ready", "paused", "active"].includes(
    sessionState,
  );
  const canArm =
    canSubmit &&
    !busy &&
    aircraftReady &&
    safetyReady &&
    (sessionReady || (canManageSession && sessionCanBePrepared)) &&
    status?.active !== true;
  const canStart = canSubmit && !busy && sessionReady && status?.armed === true;
  const canStop = canSubmit && !busy && selectedDrones.length > 0;
  const settings = (): FleetSequenceSettings => ({
    droneIds: selectedDrones.map((drone) => drone.id),
    allowedSourceNodeIds: allowedSources,
    launchIntervalSeconds,
    minimumBatteryPercent,
    instructorPresent: simulated || safetyConfirmed,
    flightAreaClear: simulated || safetyConfirmed,
    emergencyPlanReady: simulated || safetyConfirmed,
    independentRoutesConfirmed: simulated || safetyConfirmed,
  });

  return (
    <section className="fabric-panel fabric-fleet-sequence-panel">
      <header className="fabric-fleet-heading">
        <div>
          <p className="eyebrow">{t("fleet.eyebrow")}</p>
          <h2>{t("fleet.title")}</h2>
          <small>{controllerName}</small>
        </div>
        <span className={simulated ? "is-simulation" : "is-physical"}>
          {simulated ? t("brain.simulation") : t("brain.physical")}
        </span>
      </header>

      <div className="fabric-demo-status" role="status">
        <div>
          <span>{t("fleet.current")}</span>
          <strong>
            {fabricPhase(status?.phase ?? "waiting_for_status", locale)}
          </strong>
        </div>
        <div>
          <span>{t("fleet.airborne")}</span>
          <strong>
            {status?.launchedDroneIds.length ?? 0} /{" "}
            {status?.selectedDroneIds.length || selectedDrones.length}
          </strong>
        </div>
        <p>
          {status?.error ??
            (locale === "en" ? status?.message : undefined) ??
            (status === undefined
              ? t("fleet.waiting")
              : fabricPhase(status.phase, locale))}
        </p>
        <progress max={1} value={status?.progress ?? 0} />
      </div>

      <div className="fabric-fleet-aircraft">
        <strong>{t("fleet.order")}</strong>
        {selectedDrones.length === 0 ? (
          <p className="fabric-empty">{t("fleet.connectController")}</p>
        ) : (
          <ol>
            {selectedDrones.map((drone, index) => (
              <li key={drone.id}>
                <span className="fabric-fleet-order">{index + 1}</span>
                <span>
                  <strong>{drone.label}</strong>
                  <small>
                    {t("fleet.aircraftState", {
                      connection: fabricPhase(drone.connection, locale),
                      flight: fabricPhase(drone.flight, locale),
                      battery: drone.batteryPercent ?? "?",
                    })}
                  </small>
                </span>
                <span className="fabric-fleet-order-actions">
                  <button
                    type="button"
                    aria-label={t("fleet.earlier", { name: drone.label })}
                    disabled={index === 0 || status?.active === true}
                    onClick={() =>
                      setDroneOrder(move(droneOrder, index, index - 1))
                    }
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label={t("fleet.later", { name: drone.label })}
                    disabled={
                      index === selectedDrones.length - 1 ||
                      status?.active === true
                    }
                    onClick={() =>
                      setDroneOrder(move(droneOrder, index, index + 1))
                    }
                  >
                    ↓
                  </button>
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>

      <details className="fabric-fleet-options">
        <summary>
          <strong>{t("fleet.options")}</strong>
          <span>
            {t("fleet.optionsSummary", {
              interval: launchIntervalSeconds,
              battery: minimumBatteryPercent,
              inputs: allowedSources.length + 1,
            })}
          </span>
        </summary>
        <div className="fabric-fleet-options-content">
          <div className="fabric-fleet-numbers">
            <label>
              {t("fleet.interval")}
              <input
                type="number"
                min={1}
                max={15}
                step={1}
                value={launchIntervalSeconds}
                onChange={(event) =>
                  setLaunchIntervalSeconds(
                    clamp(Math.round(Number(event.target.value)), 1, 15),
                  )
                }
              />
            </label>
            <label>
              {t("fleet.minimumBattery")}
              <input
                type="number"
                min={20}
                max={100}
                step={1}
                value={minimumBatteryPercent}
                onChange={(event) =>
                  setMinimumBatteryPercent(
                    clamp(Math.round(Number(event.target.value)), 20, 100),
                  )
                }
              />
            </label>
          </div>
          <fieldset className="fabric-fleet-inputs">
            <legend>{t("fleet.inputs")}</legend>
            <label className="fabric-demo-safety-check is-fixed">
              <input type="checkbox" checked readOnly />
              <span>{t("fleet.tutorButton")}</span>
            </label>
            {inputNodes.length === 0 ? (
              <p className="fabric-empty">{t("fleet.noInputs")}</p>
            ) : (
              inputNodes.map((node) => (
                <label className="fabric-demo-safety-check" key={node.nodeId}>
                  <input
                    type="checkbox"
                    checked={allowedSources.includes(node.nodeId)}
                    disabled={status?.active === true}
                    onChange={(event) =>
                      setAllowedSources((current) =>
                        event.target.checked
                          ? [...current, node.nodeId]
                          : current.filter((id) => id !== node.nodeId),
                      )
                    }
                  />
                  <span>
                    {node.displayName} · {inputInstruction(node, t)}
                  </span>
                </label>
              ))
            )}
          </fieldset>
        </div>
      </details>

      {!simulated && (
        <div className="fabric-fleet-safety">
          <SafetyCheck
            checked={safetyConfirmed}
            onChange={onSafetyConfirmedChange}
            text={t("flight.confirmOnce")}
          />
        </div>
      )}

      {!aircraftReady && selectedDrones.length > 0 && (
        <p className="notice bad">{t("fleet.notReady")}</p>
      )}

      <div className="fabric-demo-actions fabric-fleet-actions">
        <button
          type="button"
          className={simulated ? undefined : "fabric-demo-arm"}
          disabled={!canArm}
          onClick={() =>
            onArm({
              droneIds: selectedDrones.map((drone) => drone.id),
              allowedSourceNodeIds: allowedSources,
              launchIntervalSeconds,
              minimumBatteryPercent,
              instructorPresent: simulated || safetyConfirmed,
              flightAreaClear: simulated || safetyConfirmed,
              emergencyPlanReady: simulated || safetyConfirmed,
              independentRoutesConfirmed: simulated || safetyConfirmed,
            })
          }
        >
          {t("fleet.prepareTriggers")}
        </button>
        <button
          type="button"
          className="fabric-fleet-launch"
          disabled={status?.armed === true ? !canStart : !canArm}
          onClick={
            status?.armed === true ? onStart : () => onLaunch(settings())
          }
        >
          {t("fleet.takeoffOneByOne")}
        </button>
        <button
          type="button"
          className="fabric-fleet-land"
          disabled={!canStop}
          onClick={onStop}
        >
          {t("fleet.landOneByOne")}
        </button>
      </div>
    </section>
  );
}

function SafetyCheck({
  checked,
  onChange,
  text,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  text: string;
}) {
  return (
    <label className="fabric-demo-safety-check">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>{text}</span>
    </label>
  );
}

const inputInstruction = (node: IntegrationNode, t: FabricTranslate) => {
  if (node.pluginId === "cit.leap-motion") return t("fleet.leapInstruction");
  if (node.pluginId === "cit.even-r1") return t("fleet.ringInstruction");
  return t("fleet.voiceInstruction");
};

const move = (values: string[], from: number, to: number) => {
  const result = [...values];
  const [value] = result.splice(from, 1);
  if (value !== undefined) result.splice(to, 0, value);
  return result;
};

const clamp = (value: number, minimum: number, maximum: number) =>
  Number.isFinite(value)
    ? Math.min(maximum, Math.max(minimum, value))
    : minimum;
