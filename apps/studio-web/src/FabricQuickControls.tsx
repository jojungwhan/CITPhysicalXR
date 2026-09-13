import { useEffect, useRef, useState, type FormEvent } from "react";

import type {
  FabricAndroidControllerSnapshot,
  FabricCameraImportSnapshot,
  FabricLanAccessSnapshot,
  FabricUnlockAutomationSnapshot,
} from "./fabric-client.js";
import type { FabricTranslate } from "./fabric-i18n.js";
import { FabricInfoDisclosure } from "./FabricInfoDisclosure.js";

const CAMERA_FOLDER_ACTIONS = [
  {
    cameraId: "sony-zve10-android",
    labelKey: "quickControls.sonyFolder",
  },
  {
    cameraId: "dji-osmo-nano-android",
    labelKey: "quickControls.djiFolder",
  },
] as const;

const UNLOCK_LAST_RESULT_KEYS = {
  succeeded: "settings.unlockLast.succeeded",
  failed: "settings.unlockLast.failed",
  disabled: "settings.unlockLast.disabled",
  cooldown: "settings.unlockLast.cooldown",
} as const;

export function FabricQuickControls({
  selectedPlugCount,
  canTurnOnSelected,
  canTurnOffSelected,
  busy,
  settingsOpen,
  cameras,
  canManageCamera,
  onTurnOnSelected,
  onTurnOffSelected,
  onSettingsOpenChange,
  onOpenCameraDestination,
  androidController,
  canOpenAndroidController,
  lanAccess,
  canManageLanAccess,
  unlockAutomation,
  canInstallPwa,
  onOpenAndroidController,
  onAddLanAccessDevice,
  onRemoveLanAccessDevice,
  onEnrollUsbAndroidLanAccess,
  onCopyLanAccessLink,
  onConfigureUnlockAutomation,
  onInstallAndPairUnlockCompanion,
  onRemoveUnlockCompanion,
  onInstallPwa,
  androidMode = false,
  t,
}: {
  selectedPlugCount: number;
  canTurnOnSelected: boolean;
  canTurnOffSelected: boolean;
  busy: boolean;
  settingsOpen: boolean;
  cameras: readonly FabricCameraImportSnapshot[];
  canManageCamera: boolean;
  onTurnOnSelected: () => void;
  onTurnOffSelected: () => void;
  onSettingsOpenChange: (open: boolean) => void;
  onOpenCameraDestination: (cameraId: string) => Promise<boolean>;
  androidController: FabricAndroidControllerSnapshot | null;
  canOpenAndroidController: boolean;
  lanAccess: FabricLanAccessSnapshot | null;
  canManageLanAccess: boolean;
  unlockAutomation: FabricUnlockAutomationSnapshot | null;
  canInstallPwa: boolean;
  onOpenAndroidController: () => void;
  onAddLanAccessDevice: (
    displayName: string,
    macAddress: string,
  ) => Promise<boolean>;
  onRemoveLanAccessDevice: (macAddress: string) => Promise<boolean>;
  onEnrollUsbAndroidLanAccess: () => Promise<boolean>;
  onCopyLanAccessLink: (macAddress: string) => Promise<boolean>;
  onConfigureUnlockAutomation: (
    enabled: boolean,
    selectionOnly?: boolean,
  ) => Promise<boolean>;
  onInstallAndPairUnlockCompanion: () => Promise<boolean>;
  onRemoveUnlockCompanion: () => Promise<boolean>;
  onInstallPwa: () => void;
  androidMode?: boolean;
  t: FabricTranslate;
}) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [lanDeviceName, setLanDeviceName] = useState("");
  const [lanMacAddress, setLanMacAddress] = useState("");

  const addLanDevice = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void onAddLanAccessDevice(lanDeviceName, lanMacAddress).then((saved) => {
      if (!saved) return;
      setLanDeviceName("");
      setLanMacAddress("");
    });
  };

  useEffect(() => {
    if (!settingsOpen) return;
    const previouslyFocused = document.activeElement;
    closeButtonRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onSettingsOpenChange(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
    };
  }, [onSettingsOpenChange, settingsOpen]);

  return (
    <>
      <nav
        className={`fabric-quick-controls${androidMode ? " is-android-controller" : ""}`}
        aria-label={t("quickControls.label")}
      >
        {!androidMode && (
          <>
            <span className="fabric-quick-selection" aria-live="polite">
              {t("plug.selectedCount", { count: selectedPlugCount })}
            </span>
            <button
              className="fabric-quick-plug-on"
              type="button"
              disabled={!canTurnOnSelected}
              onClick={onTurnOnSelected}
            >
              <span aria-hidden="true">●</span>
              {t("plug.turnOnSelected")}
            </button>
            <button
              className="fabric-quick-plug-off"
              type="button"
              disabled={!canTurnOffSelected}
              onClick={onTurnOffSelected}
            >
              <span aria-hidden="true">○</span>
              {t("plug.turnOffSelected")}
            </button>
          </>
        )}
        {CAMERA_FOLDER_ACTIONS.map(({ cameraId, labelKey }) => {
          const camera = cameras.find((item) => item.cameraId === cameraId);
          return (
            <button
              className="fabric-quick-camera-folder"
              key={cameraId}
              type="button"
              disabled={
                !canManageCamera ||
                busy ||
                camera?.operations.openDestination !== true
              }
              onClick={() => {
                if (camera !== undefined) {
                  void onOpenCameraDestination(camera.cameraId);
                }
              }}
            >
              <span aria-hidden="true">▣</span>
              {t(labelKey)}
            </button>
          );
        })}
        {!androidMode && (
          <a
            className="fabric-quick-social-content"
            href="http://127.0.0.1:4174"
            target="_blank"
            rel="noreferrer"
          >
            <span aria-hidden="true">✦</span>
            {t("quickControls.socialContent")}
          </a>
        )}
        <button
          className="fabric-quick-settings"
          type="button"
          aria-expanded={settingsOpen}
          aria-controls="fabric-control-settings"
          onClick={() => onSettingsOpenChange(!settingsOpen)}
        >
          <span aria-hidden="true">⚙</span>
          {t("quickControls.settings")}
        </button>
      </nav>

      {settingsOpen && (
        <div className="fabric-settings-backdrop">
          <section
            className="fabric-settings-dialog"
            id="fabric-control-settings"
            role="dialog"
            aria-modal="true"
            aria-labelledby="fabric-control-settings-title"
          >
            <header>
              <div>
                <p className="eyebrow">{t("settings.eyebrow")}</p>
                <h2 id="fabric-control-settings-title">
                  {t("settings.title")}
                </h2>
              </div>
              <button
                ref={closeButtonRef}
                className="fabric-settings-close"
                type="button"
                aria-label={t("quickControls.closeSettings")}
                onClick={() => onSettingsOpenChange(false)}
              >
                ×
              </button>
            </header>

            <p className="fabric-settings-intro">{t("settings.intro")}</p>

            <section className="fabric-settings-group">
              <h3>{t("settings.cameraImport")}</h3>
              {cameras.length === 0 ? (
                <p>{t("cameraImport.loading")}</p>
              ) : (
                cameras.map((camera) => {
                  const scheduleMinutes =
                    camera.automaticIntervalSeconds === undefined
                      ? undefined
                      : Math.max(
                          1,
                          Math.round(camera.automaticIntervalSeconds / 60),
                        );
                  return (
                    <article
                      className="fabric-settings-camera"
                      key={camera.cameraId}
                    >
                      <h4>{camera.displayName}</h4>
                      <div className="fabric-settings-field">
                        <span>{t("cameraImport.destination")}</span>
                        <code>{camera.destination}</code>
                      </div>
                      <div className="fabric-settings-field">
                        <span>{t("cameraImport.schedule")}</span>
                        <strong>
                          {camera.automaticEnabled &&
                          scheduleMinutes !== undefined
                            ? t("cameraImport.scheduleEnabled", {
                                minutes: scheduleMinutes,
                              })
                            : t("cameraImport.scheduleDisabled")}
                        </strong>
                      </div>
                      <button
                        type="button"
                        disabled={
                          !canManageCamera ||
                          busy ||
                          !camera.operations.openDestination
                        }
                        onClick={() =>
                          void onOpenCameraDestination(camera.cameraId)
                        }
                      >
                        {t("cameraImport.openDestination")}
                      </button>
                    </article>
                  );
                })
              )}
            </section>

            <section className="fabric-settings-group">
              <h3>{t("settings.smartPlugs")}</h3>
              <p>
                {t("settings.smartPlugSelection", {
                  count: selectedPlugCount,
                })}
              </p>
            </section>

            {canManageLanAccess && (
              <section className="fabric-settings-group fabric-unlock-automation">
                <div className="fabric-settings-group-heading">
                  <h3>{t("settings.unlockAutomation")}</h3>
                  <FabricInfoDisclosure label={t("common.moreInfo")}>
                    <p>{t("settings.unlockAutomationHelp")}</p>
                    <p>{t("settings.unlockAutomationOffline")}</p>
                  </FabricInfoDisclosure>
                </div>
                <div className="fabric-settings-field">
                  <span>{t("settings.unlockPhone")}</span>
                  <strong>
                    {unlockAutomation?.companion?.displayName ??
                      t("settings.unlockNotPaired")}
                  </strong>
                </div>
                <div className="fabric-settings-field">
                  <span>{t("settings.unlockConfiguredPlugs")}</span>
                  <strong>
                    {t("settings.unlockPlugCount", {
                      count: unlockAutomation?.selectedNodeIds.length ?? 0,
                    })}
                  </strong>
                </div>
                <label className="fabric-unlock-toggle">
                  <input
                    type="checkbox"
                    checked={unlockAutomation?.enabled === true}
                    disabled={
                      busy ||
                      unlockAutomation?.operations.manage !== true ||
                      unlockAutomation.companion === undefined ||
                      (unlockAutomation.enabled !== true &&
                        selectedPlugCount === 0)
                    }
                    onChange={(event) =>
                      void onConfigureUnlockAutomation(event.target.checked)
                    }
                  />
                  <span>{t("settings.unlockToggle")}</span>
                </label>
                <div className="fabric-settings-actions">
                  <button
                    type="button"
                    disabled={
                      busy ||
                      selectedPlugCount === 0 ||
                      unlockAutomation?.operations.manage !== true ||
                      unlockAutomation.companion === undefined
                    }
                    onClick={() =>
                      void onConfigureUnlockAutomation(
                        unlockAutomation?.enabled === true,
                        true,
                      )
                    }
                  >
                    {t("settings.unlockSaveSelection")}
                  </button>
                  {unlockAutomation?.companion === undefined ? (
                    <button
                      type="button"
                      disabled={
                        busy ||
                        unlockAutomation?.operations.installAndPair !== true
                      }
                      onClick={() => void onInstallAndPairUnlockCompanion()}
                    >
                      {t("settings.unlockInstallPair")}
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={
                        busy || unlockAutomation.operations.manage !== true
                      }
                      onClick={() => void onRemoveUnlockCompanion()}
                    >
                      {t("settings.unlockRemovePhone")}
                    </button>
                  )}
                </div>
                <p>{t("settings.unlockInstallHelp")}</p>
                {unlockAutomation?.lastResult !== undefined && (
                  <p className="fabric-unlock-last-result" aria-live="polite">
                    {t(
                      UNLOCK_LAST_RESULT_KEYS[
                        unlockAutomation.lastResult.outcome
                      ],
                      {
                        accepted: unlockAutomation.lastResult.acceptedCount,
                        count: unlockAutomation.lastResult.requestedCount,
                      },
                    )}
                  </p>
                )}
              </section>
            )}

            <section className="fabric-settings-group">
              <h3>{t("settings.androidController")}</h3>
              <p>{t("settings.androidHelp")}</p>
              <div className="fabric-settings-field">
                <span>{t("settings.androidPhone")}</span>
                <strong>
                  {androidController?.phoneModel ??
                    t(
                      `settings.androidState.${androidController?.state ?? "checking"}`,
                    )}
                </strong>
              </div>
              {androidController?.phoneModel !== undefined && (
                <p>{t(`settings.androidState.${androidController.state}`)}</p>
              )}
              <div className="fabric-settings-actions">
                <button
                  type="button"
                  disabled={
                    busy ||
                    !canOpenAndroidController ||
                    androidController?.operations.openController !== true
                  }
                  onClick={onOpenAndroidController}
                >
                  {t("settings.androidOpen")}
                </button>
                {canInstallPwa && (
                  <button type="button" disabled={busy} onClick={onInstallPwa}>
                    {t("settings.androidInstall")}
                  </button>
                )}
              </div>
              <p>{t("settings.androidInstallHelp")}</p>
            </section>

            {canManageLanAccess && (
              <section className="fabric-settings-group fabric-lan-access">
                <div className="fabric-settings-group-heading">
                  <h3>{t("settings.lanAccess")}</h3>
                  <FabricInfoDisclosure label={t("common.moreInfo")}>
                    <p>{t("settings.lanAccessHelp")}</p>
                    <p>{t("settings.lanEnrollAndroidHelp")}</p>
                  </FabricInfoDisclosure>
                </div>
                <div className="fabric-settings-field">
                  <span>{t("settings.lanAddress")}</span>
                  <code>
                    {lanAccess?.lanOrigin ??
                      t("settings.lanAddressUnavailable")}
                  </code>
                </div>
                <strong className="fabric-lan-access-status">
                  {t(
                    lanAccess?.enabled
                      ? "settings.lanEnabled"
                      : "settings.lanDisabled",
                  )}
                </strong>
                <button
                  type="button"
                  disabled={
                    busy || lanAccess?.operations.enrollUsbAndroid !== true
                  }
                  onClick={() => void onEnrollUsbAndroidLanAccess()}
                >
                  {t("settings.lanEnrollAndroid")}
                </button>

                {lanAccess !== null && lanAccess.devices.length > 0 ? (
                  <ul className="fabric-lan-device-list">
                    {lanAccess.devices.map((device) => (
                      <li key={device.macAddress}>
                        <span>
                          <strong>{device.displayName}</strong>
                          <code>{device.macAddress}</code>
                        </span>
                        <div className="fabric-lan-device-actions">
                          <button
                            type="button"
                            disabled={busy || !lanAccess.operations.manage}
                            onClick={() =>
                              void onCopyLanAccessLink(device.macAddress)
                            }
                          >
                            {t("settings.lanCopyLink")}
                          </button>
                          <button
                            type="button"
                            disabled={busy || !lanAccess.operations.manage}
                            aria-label={t("settings.lanRemoveNamed", {
                              name: device.displayName,
                            })}
                            onClick={() =>
                              void onRemoveLanAccessDevice(device.macAddress)
                            }
                          >
                            {t("settings.lanRemove")}
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>{t("settings.lanNoDevices")}</p>
                )}

                <form
                  className="fabric-lan-device-form"
                  onSubmit={addLanDevice}
                >
                  <label>
                    <span>{t("settings.lanDeviceName")}</span>
                    <input
                      value={lanDeviceName}
                      maxLength={80}
                      autoComplete="off"
                      required
                      onChange={(event) => setLanDeviceName(event.target.value)}
                    />
                  </label>
                  <label>
                    <span>{t("settings.lanMacAddress")}</span>
                    <input
                      value={lanMacAddress}
                      maxLength={17}
                      autoCapitalize="none"
                      autoComplete="off"
                      spellCheck={false}
                      placeholder="00:11:22:33:44:55"
                      required
                      onChange={(event) => setLanMacAddress(event.target.value)}
                    />
                  </label>
                  <button
                    type="submit"
                    disabled={
                      busy ||
                      lanDeviceName.trim() === "" ||
                      lanMacAddress.trim() === "" ||
                      lanAccess?.operations.manage !== true
                    }
                  >
                    {t("settings.lanAdd")}
                  </button>
                </form>
              </section>
            )}
          </section>
        </div>
      )}
    </>
  );
}
