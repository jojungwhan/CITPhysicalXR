import type { Translate } from "./i18n.js";
import type { DeviceView, HealthView, SessionView } from "./runtime-client.js";

/**
 * UI 11.4. The four states have to be unmistakable.
 *
 * Colour alone is not enough -- it fails for a colour-blind student and for a
 * projector -- so each state carries a word, a shape, and a sentence saying what
 * it means for the robot on the desk. The state is derived from what the runtime
 * reports rather than from what this page last did, so a banner cannot go stale
 * by disagreeing with the machine that actually refuses commands.
 */
export type SafetyState =
  "simulation" | "physicalDisarmed" | "physicalArmed" | "emergencyStopped";

const SYMBOL: Record<SafetyState, string> = {
  simulation: "◇",
  physicalDisarmed: "▣",
  physicalArmed: "▲",
  emergencyStopped: "■",
};

export function safetyStateOf(input: {
  health: HealthView | null;
  devices: DeviceView[];
  sessions: SessionView[];
}): SafetyState {
  if (input.sessions.some((session) => session.state === "emergency_stopped")) {
    return "emergencyStopped";
  }
  if (input.health === null || !input.health.physicalEnabled)
    return "simulation";
  const physical = input.devices.filter((device) => device.physical);
  if (physical.length === 0) return "simulation";
  return physical.some((device) => device.armed)
    ? "physicalArmed"
    : "physicalDisarmed";
}

export function SafetyBanner({
  state,
  t,
}: {
  state: SafetyState;
  t: Translate;
}) {
  return (
    <div className={`safety ${state}`} role="status" aria-live="polite">
      <span className="safety-symbol" aria-hidden="true">
        {SYMBOL[state]}
      </span>
      <strong className="safety-label">{t(`safety.${state}`)}</strong>
      <span className="safety-meaning">{t(`safety.${state}Meaning`)}</span>
    </div>
  );
}
