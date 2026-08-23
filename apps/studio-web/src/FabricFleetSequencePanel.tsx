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
  onArm: (settings: FleetSequenceSettings) => void;
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
  onArm,
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
  const [droneOrder, setDroneOrder] = useState<string[]>([]);
  const [allowedSources, setAllowedSources] = useState<string[]>([]);
  const [launchIntervalSeconds, setLaunchIntervalSeconds] = useState(2);
  const [minimumBatteryPercent, setMinimumBatteryPercent] = useState(30);
  const [instructorPresent, setInstructorPresent] = useState(false);
  const [flightAreaClear, setFlightAreaClear] = useState(false);
  const [emergencyPlanReady, setEmergencyPlanReady] = useState(false);
  const [independentRoutesConfirmed, setIndependentRoutesConfirmed] =
    useState(false);

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
    selectedDrones.length >= 2 &&
    selectedDrones.every(
      (drone) =>
        drone.connection === "connected" &&
        drone.flight === "landed" &&
        drone.batteryPercent !== undefined &&
        drone.batteryPercent >= minimumBatteryPercent,
    );
  const safetyReady =
    simulated ||
    (instructorPresent &&
      flightAreaClear &&
      emergencyPlanReady &&
      independentRoutesConfirmed);
  const sessionReady = sessionState === "active" && (simulated || sessionArmed);
  const canArm =
    canSubmit &&
    !busy &&
    aircraftReady &&
    safetyReady &&
    sessionReady &&
    status?.active !== true;
  const canStart = canSubmit && !busy && sessionReady && status?.armed === true;
  const canStop = canSubmit && !busy;

  return (
    <section className="fabric-panel fabric-fleet-sequence-panel">
      <div className="fabric-panel-heading">
        <p className="eyebrow">{t("fleet.eyebrow")}</p>
        <h2>{t("fleet.title")}</h2>
      </div>
      <div
        className={`fabric-demo-mode ${simulated ? "is-simulation" : "is-physical"}`}
      >
        <strong>
          {simulated ? t("brain.simulation") : t("brain.physical")}
        </strong>
        <span>{controllerName}</span>
      </div>
      <p className="fabric-help">
        {t("fleet.helpBefore")} <strong>{t("fleet.startNow")}</strong>,{" "}
        {t("fleet.helpAfter")}
      </p>

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
            {status?.selectedDroneIds.length ?? 0}
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

      <fieldset className="fabric-fleet-aircraft">
        <legend>{t("fleet.order")}</legend>
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
                  <button
                    type="button"
                    disabled={
                      selectedDrones.length <= 2 || status?.active === true
                    }
                    onClick={() =>
                      setDroneOrder(droneOrder.filter((id) => id !== drone.id))
                    }
                  >
                    {t("fleet.remove")}
                  </button>
                </span>
              </li>
            ))}
          </ol>
        )}
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
      </fieldset>

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

      {!simulated && (
        <fieldset className="fabric-demo-checklist">
          <legend>{t("fleet.flightCheck")}</legend>
          <SafetyCheck
            checked={instructorPresent}
            onChange={setInstructorPresent}
            text={t("fleet.present")}
          />
          <SafetyCheck
            checked={flightAreaClear}
            onChange={setFlightAreaClear}
            text={t("fleet.areaClear")}
          />
          <SafetyCheck
            checked={emergencyPlanReady}
            onChange={setEmergencyPlanReady}
            text={t("fleet.emergencyReady")}
          />
          <SafetyCheck
            checked={independentRoutesConfirmed}
            onChange={setIndependentRoutesConfirmed}
            text={t("fleet.routes")}
          />
        </fieldset>
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
              instructorPresent: simulated || instructorPresent,
              flightAreaClear: simulated || flightAreaClear,
              emergencyPlanReady: simulated || emergencyPlanReady,
              independentRoutesConfirmed:
                simulated || independentRoutesConfirmed,
            })
          }
        >
          {t("fleet.arm")}
          <small>
            {sessionReady ? t("fleet.armHelp") : t("fleet.startArmFirst")}
          </small>
        </button>
        <button type="button" disabled={!canStart} onClick={onStart}>
          {t("fleet.startNow")}
          <small>{t("fleet.startHelp")}</small>
        </button>
        <button
          type="button"
          className="fabric-drone-emergency"
          disabled={!canStop}
          onClick={onStop}
        >
          {t("fleet.stop")}
          <small>{t("fleet.stopHelp")}</small>
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
