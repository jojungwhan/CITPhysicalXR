import { useState } from "react";

import type {
  BrainDemoSettings,
  BrainDemoStatus,
} from "./fabric-brain-demo.js";
import { fabricPhase, type FabricTranslate } from "./fabric-i18n.js";
import type { Locale } from "./i18n.js";

interface FabricBrainDemoPanelProps {
  controllerName: string;
  simulated: boolean;
  status?: BrainDemoStatus;
  sessionState: string;
  sessionArmed: boolean;
  busy: boolean;
  canSubmit: boolean;
  canManageSession: boolean;
  safetyConfirmed: boolean;
  onSafetyConfirmedChange: (confirmed: boolean) => void;
  onArm: (settings: BrainDemoSettings) => void;
  onStop: () => void;
  locale: Locale;
  t: FabricTranslate;
}

export function FabricBrainDemoPanel({
  controllerName,
  simulated,
  status,
  sessionState,
  sessionArmed,
  busy,
  canSubmit,
  canManageSession,
  safetyConfirmed,
  onSafetyConfirmedChange,
  onArm,
  onStop,
  locale,
  t,
}: FabricBrainDemoPanelProps) {
  const [attentionEnabled, setAttentionEnabled] = useState(true);
  const [attentionThreshold, setAttentionThreshold] = useState(50);
  const [meditationEnabled, setMeditationEnabled] = useState(false);
  const [meditationThreshold, setMeditationThreshold] = useState(50);
  const [blinkEnabled, setBlinkEnabled] = useState(false);
  const [blinkThreshold, setBlinkThreshold] = useState(50);
  const [dwellSeconds, setDwellSeconds] = useState(2);
  const signalSelected = attentionEnabled || meditationEnabled || blinkEnabled;
  const safetyReady = simulated || safetyConfirmed;
  const sessionReady = sessionState === "active" && (simulated || sessionArmed);
  const sessionCanBePrepared = ["ready", "paused", "active"].includes(
    sessionState,
  );
  const canArm =
    canSubmit &&
    !busy &&
    signalSelected &&
    safetyReady &&
    (sessionReady || (canManageSession && sessionCanBePrepared)) &&
    status?.armed !== true &&
    status?.demoRunning !== true;
  const canStop = canSubmit && !busy;

  return (
    <section className="fabric-panel fabric-brain-demo-panel">
      <div className="fabric-panel-heading">
        <p className="eyebrow">{t("brain.eyebrow")}</p>
        <h2>{t("brain.title")}</h2>
      </div>
      <div
        className={`fabric-demo-mode ${simulated ? "is-simulation" : "is-physical"}`}
      >
        <strong>
          {simulated ? t("brain.simulation") : t("brain.physical")}
        </strong>
        <span>{controllerName}</span>
      </div>
      <p className="fabric-help">{t("brain.help")}</p>

      <div className="fabric-demo-status" role="status">
        <div>
          <span>{t("brain.current")}</span>
          <strong>
            {fabricPhase(status?.phase ?? "waiting_for_status", locale)}
          </strong>
        </div>
        <div>
          <span>{t("brain.progress")}</span>
          <strong>{Math.round((status?.progress ?? 0) * 100)}%</strong>
        </div>
        <p>
          {status?.error ??
            (locale === "en" ? status?.message : undefined) ??
            (status === undefined
              ? t("brain.waiting")
              : fabricPhase(status.phase, locale))}
        </p>
        <progress max={1} value={status?.progress ?? 0} />
      </div>

      <fieldset className="fabric-demo-signals">
        <legend>{t("brain.chooseSignal")}</legend>
        <SignalSetting
          checked={attentionEnabled}
          label={t("brain.attention")}
          help={t("brain.attentionHelp")}
          thresholdLabel={t("brain.threshold", { label: t("brain.attention") })}
          value={attentionThreshold}
          minimum={1}
          maximum={100}
          onChecked={setAttentionEnabled}
          onValue={setAttentionThreshold}
        />
        <SignalSetting
          checked={meditationEnabled}
          label={t("brain.meditation")}
          help={t("brain.meditationHelp")}
          thresholdLabel={t("brain.threshold", {
            label: t("brain.meditation"),
          })}
          value={meditationThreshold}
          minimum={1}
          maximum={100}
          onChecked={setMeditationEnabled}
          onValue={setMeditationThreshold}
        />
        <SignalSetting
          checked={blinkEnabled}
          label={t("brain.blink")}
          help={t("brain.blinkHelp")}
          thresholdLabel={t("brain.threshold", { label: t("brain.blink") })}
          value={blinkThreshold}
          minimum={0}
          maximum={254}
          onChecked={setBlinkEnabled}
          onValue={setBlinkThreshold}
        />
        <label className="fabric-demo-dwell">
          {t("brain.hold")}
          <span>
            <input
              type="number"
              min={0}
              max={10}
              step={0.5}
              value={dwellSeconds}
              onChange={(event) =>
                setDwellSeconds(clamp(Number(event.target.value), 0, 10))
              }
            />
            {t("brain.seconds")}
          </span>
          <small>{t("brain.dwellHelp")}</small>
        </label>
      </fieldset>

      {!simulated && (
        <fieldset className="fabric-demo-checklist">
          <legend>{t("brain.flightCheck")}</legend>
          <SafetyCheck
            checked={safetyConfirmed}
            onChange={onSafetyConfirmedChange}
            text={t("flight.confirmOnce")}
          />
        </fieldset>
      )}

      <div className="fabric-demo-actions">
        <button
          type="button"
          className={simulated ? undefined : "fabric-demo-arm"}
          disabled={!canArm}
          onClick={() =>
            onArm({
              attentionEnabled,
              attentionThreshold,
              meditationEnabled,
              meditationThreshold,
              blinkEnabled,
              blinkThreshold,
              dwellSeconds,
              instructorPresent: simulated || safetyConfirmed,
              flightAreaClear: simulated || safetyConfirmed,
              emergencyPlanReady: simulated || safetyConfirmed,
            })
          }
        >
          {simulated ? t("brain.runSimulation") : t("brain.arm")}
          <small>
            {sessionReady
              ? t("brain.waitCondition")
              : simulated
                ? t("brain.startFirst")
                : t("brain.startArmFirst")}
          </small>
        </button>
        <button type="button" disabled={!canStop} onClick={onStop}>
          {t("brain.stop")}
          <small>{t("brain.stopHelp")}</small>
        </button>
      </div>
    </section>
  );
}

function SignalSetting({
  checked,
  label,
  thresholdLabel,
  help,
  value,
  minimum,
  maximum,
  onChecked,
  onValue,
}: {
  checked: boolean;
  label: string;
  thresholdLabel: string;
  help: string;
  value: number;
  minimum: number;
  maximum: number;
  onChecked: (checked: boolean) => void;
  onValue: (value: number) => void;
}) {
  return (
    <div className={`fabric-demo-signal ${checked ? "is-enabled" : ""}`}>
      <label>
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => onChecked(event.target.checked)}
        />
        <strong>{label}</strong>
      </label>
      <input
        aria-label={thresholdLabel}
        type="number"
        min={minimum}
        max={maximum}
        step={1}
        disabled={!checked}
        value={value}
        onChange={(event) =>
          onValue(
            clamp(Math.round(Number(event.target.value)), minimum, maximum),
          )
        }
      />
      <small>{help}</small>
    </div>
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

const clamp = (value: number, minimum: number, maximum: number) =>
  Number.isFinite(value)
    ? Math.min(maximum, Math.max(minimum, value))
    : minimum;
