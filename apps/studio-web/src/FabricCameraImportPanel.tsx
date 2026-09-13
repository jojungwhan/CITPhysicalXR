import type {
  FabricCameraImportBattery,
  FabricCameraImportSnapshot,
} from "./fabric-client.js";
import type { FabricTranslate } from "./fabric-i18n.js";
import { FabricInfoDisclosure } from "./FabricInfoDisclosure.js";

const ACTIVE_STATES = new Set<FabricCameraImportSnapshot["state"]>([
  "connecting",
  "inventory",
  "transferring",
  "copying",
  "verifying",
]);

export function FabricCameraImportPanel({
  camera,
  busy,
  canManage,
  onStart,
  onOpenDestination,
  t,
}: {
  camera: FabricCameraImportSnapshot | null;
  busy: boolean;
  canManage: boolean;
  onStart: () => Promise<boolean>;
  onOpenDestination: () => Promise<boolean>;
  t: FabricTranslate;
}) {
  if (camera === null) {
    return (
      <section className="fabric-panel fabric-camera-import" aria-busy="true">
        <p className="eyebrow">{t("cameraImport.eyebrow")}</p>
        <h2>{t("cameraImport.genericTitle")}</h2>
        <p>{t("cameraImport.loading")}</p>
      </section>
    );
  }

  const active = ACTIVE_STATES.has(camera.state);
  const stateKey = `cameraImport.state.${camera.state}` as const;
  const phoneUnlockRequired = camera.errorCode?.endsWith(
    "_PHONE_UNLOCK_REQUIRED",
  );
  const isDji = camera.cameraId === "dji-osmo-nano-android";
  const panelId = `camera-import-${camera.cameraId.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const titleId = `${panelId}-title`;
  const setupTitleKey = phoneUnlockRequired
    ? "cameraImport.phoneUnlockTitle"
    : isDji
      ? "cameraImport.djiSetupTitle"
      : "cameraImport.setupTitle";
  const setupBodyKey = phoneUnlockRequired
    ? "cameraImport.phoneUnlockBody"
    : isDji
      ? "cameraImport.djiSetupBody"
      : "cameraImport.setupBody";
  const automationHelpKey = isDji
    ? "cameraImport.djiAutomationHelp"
    : "cameraImport.automationHelp";
  const pairingHelpKey = isDji
    ? "cameraImport.djiPairingHelp"
    : "cameraImport.pairingHelp";
  const scheduleMinutes =
    camera.automaticIntervalSeconds === undefined
      ? undefined
      : Math.max(1, Math.round(camera.automaticIntervalSeconds / 60));
  const phoneBattery = camera.phoneBattery ?? { condition: "unknown" };
  const cameraBattery = camera.cameraBattery ?? { condition: "unknown" };
  const batteryDeferred =
    phoneBattery.condition === "blocked" ||
    cameraBattery.condition === "blocked";

  return (
    <section
      className={`fabric-panel fabric-camera-import is-${camera.state}`}
      id={panelId}
      aria-labelledby={titleId}
      aria-busy={active}
    >
      <div className="fabric-camera-import-heading">
        <div>
          <p className="eyebrow">{t("cameraImport.eyebrow")}</p>
          <h2 id={titleId}>
            {t("cameraImport.title", { camera: camera.displayName })}
          </h2>
        </div>
        <span className={`fabric-camera-import-state is-${camera.state}`}>
          {t(stateKey)}
        </span>
      </div>

      <div className="fabric-camera-import-identity">
        <div>
          <small>{t("cameraImport.camera")}</small>
          <strong>{camera.displayName}</strong>
        </div>
        <div
          className={`fabric-camera-import-battery is-${cameraBattery.condition}`}
        >
          <small>{t("cameraImport.cameraBattery")}</small>
          <strong>{formatBattery(cameraBattery, t)}</strong>
        </div>
        <div>
          <small>{t("cameraImport.phone")}</small>
          <strong>
            {camera.phoneConnected
              ? (camera.phoneModel ?? t("cameraImport.phoneConnected"))
              : t("cameraImport.phoneDisconnected")}
          </strong>
        </div>
        <div
          className={`fabric-camera-import-battery is-${phoneBattery.condition}`}
        >
          <small>{t("cameraImport.phoneBattery")}</small>
          <strong>{formatBattery(phoneBattery, t)}</strong>
        </div>
        <div>
          <small>{t("cameraImport.onPhone")}</small>
          <strong>
            {t("cameraImport.fileSummary", {
              count: camera.filesOnPhone,
              size: formatBytes(camera.bytesOnPhone),
            })}
          </strong>
        </div>
        <div>
          <small>{t("cameraImport.schedule")}</small>
          <strong>
            {camera.automaticEnabled && scheduleMinutes !== undefined
              ? t("cameraImport.scheduleEnabled", {
                  minutes: scheduleMinutes,
                })
              : t("cameraImport.scheduleDisabled")}
          </strong>
        </div>
      </div>

      {camera.setupRequired && (
        <div className="fabric-camera-import-setup" role="status">
          <strong>{t(setupTitleKey)}</strong>
          <span>{t(setupBodyKey)}</span>
        </div>
      )}

      {batteryDeferred && (
        <div className="fabric-camera-import-battery-note" role="status">
          <strong>{t("cameraImport.batteryDeferredTitle")}</strong>
          <span>{t("cameraImport.batteryDeferredBody")}</span>
        </div>
      )}

      {camera.progress !== undefined && (
        <div className="fabric-camera-import-progress" role="status">
          <strong>{t(stateKey)}</strong>
          {camera.progress.totalItems !== undefined && (
            <>
              <span>
                {t("cameraImport.progressCount", {
                  completed: camera.progress.completedItems,
                  total: camera.progress.totalItems,
                })}
              </span>
              <progress
                max={camera.progress.totalItems}
                value={camera.progress.completedItems}
                aria-label={t("cameraImport.progress")}
              />
            </>
          )}
        </div>
      )}

      {camera.lastResult !== undefined && !active && (
        <div className="fabric-camera-import-result">
          <strong>{t("cameraImport.verified")}</strong>
          <span>
            {t("cameraImport.result", {
              copied: camera.lastResult.copiedFiles,
              skipped: camera.lastResult.skippedFiles,
              verified: camera.lastResult.verifiedFiles,
              size: formatBytes(camera.lastResult.totalBytes),
            })}
          </span>
        </div>
      )}

      <div className="fabric-camera-import-actions">
        <div className="fabric-camera-import-primary-actions">
          <button
            type="button"
            disabled={
              !canManage || busy || active || !camera.operations.startImport
            }
            onClick={() => void onStart()}
          >
            {active ? t("cameraImport.running") : t("cameraImport.start")}
          </button>
          <button
            className="fabric-camera-import-open-destination"
            type="button"
            disabled={!canManage || busy || !camera.operations.openDestination}
            onClick={() => void onOpenDestination()}
          >
            <span aria-hidden="true">▣</span>
            {t("cameraImport.openDestination")}
          </button>
        </div>
        <FabricInfoDisclosure label={t("common.moreInfo")}>
          <p>{t(automationHelpKey)}</p>
          {camera.automaticEnabled && scheduleMinutes !== undefined && (
            <p>
              {t("cameraImport.scheduleHelp", {
                minutes: scheduleMinutes,
              })}
            </p>
          )}
          <p>{t(pairingHelpKey)}</p>
          <p>{t("cameraImport.batteryHelp")}</p>
          <p>{t("cameraImport.safetyHelp")}</p>
        </FabricInfoDisclosure>
      </div>
    </section>
  );
}

const formatBytes = (bytes: number): string => {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
};

const formatBattery = (
  battery: FabricCameraImportBattery,
  t: FabricTranslate,
): string => {
  if (battery.levelPercent === undefined) {
    return t("cameraImport.batteryUnknown");
  }
  if (battery.condition === "blocked") {
    return t("cameraImport.batteryBlocked", { level: battery.levelPercent });
  }
  if (battery.charging === true) {
    return t("cameraImport.batteryCharging", { level: battery.levelPercent });
  }
  if (battery.condition === "warning") {
    return t("cameraImport.batteryWarning", { level: battery.levelPercent });
  }
  return t("cameraImport.batteryLevel", { level: battery.levelPercent });
};
