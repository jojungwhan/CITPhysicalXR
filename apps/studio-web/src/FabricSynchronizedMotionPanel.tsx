import type { FabricTranslate } from "./fabric-i18n.js";
import type {
  SynchronizedInputKind,
  SynchronizedMotionDirection,
} from "./fabric-synchronized-motion.js";

const INPUTS: readonly SynchronizedInputKind[] = [
  "g2",
  "r1",
  "meta",
  "mindwave",
];
const INPUT_LABEL_KEYS = {
  g2: "sync.input.g2",
  r1: "sync.input.r1",
  meta: "sync.input.meta",
  mindwave: "sync.input.mindwave",
} as const;

export function FabricSynchronizedMotionPanel({
  enabled,
  includeTello,
  groundCount,
  telloCount,
  availableInputs,
  busy,
  canManage,
  flightConfirmed,
  onEnabledChange,
  onIncludeTelloChange,
  onAssignInputs,
  onMove,
  t,
}: {
  enabled: boolean;
  includeTello: boolean;
  groundCount: number;
  telloCount: number;
  availableInputs: ReadonlySet<SynchronizedInputKind>;
  busy: boolean;
  canManage: boolean;
  flightConfirmed: boolean;
  onEnabledChange: (enabled: boolean) => void;
  onIncludeTelloChange: (included: boolean) => void;
  onAssignInputs: () => void;
  onMove: (direction: SynchronizedMotionDirection) => void;
  t: FabricTranslate;
}) {
  const groundReady = groundCount > 0;
  const canMove = enabled && groundReady && canManage && !busy;
  const telloSelectable = telloCount > 0 && flightConfirmed;

  return (
    <section
      className="fabric-synchronized-motion"
      aria-labelledby="synchronized-motion-title"
    >
      <header>
        <div>
          <p className="eyebrow">{t("sync.eyebrow")}</p>
          <h3 id="synchronized-motion-title">{t("sync.title")}</h3>
        </div>
        <label className="fabric-sync-master">
          <input
            type="checkbox"
            checked={enabled}
            disabled={!canManage || busy || !groundReady}
            onChange={(event) => onEnabledChange(event.target.checked)}
          />
          <span>{t("sync.enable")}</span>
        </label>
      </header>

      <div className="fabric-sync-body">
        <div className="fabric-sync-targets">
          <strong>{t("sync.groundTargets", { count: groundCount })}</strong>
          <label>
            <input
              type="checkbox"
              checked={includeTello}
              disabled={!enabled || busy || !telloSelectable}
              onChange={(event) => onIncludeTelloChange(event.target.checked)}
            />
            <span>{t("sync.includeTello", { count: telloCount })}</span>
          </label>
          {telloCount > 0 && !flightConfirmed && (
            <small>{t("sync.telloSafety")}</small>
          )}
        </div>

        <div className="fabric-sync-pad" aria-label={t("sync.controls")}>
          <button
            type="button"
            disabled={!canMove}
            aria-label={t("sync.forward")}
            onClick={() => onMove("forward")}
          >
            ↑
          </button>
          <button
            type="button"
            disabled={!canMove}
            aria-label={t("sync.left")}
            onClick={() => onMove("left")}
          >
            ←
          </button>
          <button
            className="is-stop"
            type="button"
            disabled={!enabled || !canManage || busy || !groundReady}
            aria-label={t("sync.stop")}
            onClick={() => onMove("stop")}
          >
            ■
          </button>
          <button
            type="button"
            disabled={!canMove}
            aria-label={t("sync.right")}
            onClick={() => onMove("right")}
          >
            →
          </button>
          <button
            type="button"
            disabled={!canMove}
            aria-label={t("sync.backward")}
            onClick={() => onMove("backward")}
          >
            ↓
          </button>
        </div>

        <div className="fabric-sync-inputs">
          <div>
            <strong>{t("sync.inputs")}</strong>
            <span>
              {INPUTS.map((kind) => (
                <em
                  className={availableInputs.has(kind) ? "is-ready" : undefined}
                  key={kind}
                >
                  {t(INPUT_LABEL_KEYS[kind])}
                </em>
              ))}
            </span>
          </div>
          <button
            type="button"
            disabled={!enabled || busy || !canManage}
            onClick={onAssignInputs}
          >
            {t("sync.connectWearables")}
          </button>
          <small>{t("sync.inputHelp")}</small>
        </div>
      </div>
    </section>
  );
}
