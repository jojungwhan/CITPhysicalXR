import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import type {
  FabricPrinterGcodeArtifact,
  FabricPrinterSnapshot,
  FabricPrinterStartIntent,
} from "./fabric-client.js";
import type { FabricMessageKey, FabricTranslate } from "./fabric-i18n.js";
import { FabricInfoDisclosure } from "./FabricInfoDisclosure.js";

export function FabricPrinterPanel({
  printer,
  busy,
  canManage,
  onVerifyIdle,
  onStage,
  onSlice,
  onDownload,
  onUpload,
  onPrepareStart,
  onStart,
  t,
}: {
  printer: FabricPrinterSnapshot | null;
  busy: boolean;
  canManage: boolean;
  onVerifyIdle: () => Promise<boolean>;
  onStage: (file: File) => Promise<boolean>;
  onSlice: (sourceId: string, profileId: string) => Promise<boolean>;
  onDownload: (artifact: FabricPrinterGcodeArtifact) => Promise<boolean>;
  onUpload: (artifactId: string) => Promise<boolean>;
  onPrepareStart: (
    artifactId: string,
  ) => Promise<FabricPrinterStartIntent | undefined>;
  onStart: (artifactId: string, confirmationToken: string) => Promise<boolean>;
  t: FabricTranslate;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [profileId, setProfileId] = useState("");
  const [startIntent, setStartIntent] = useState<FabricPrinterStartIntent>();
  const [plateClear, setPlateClear] = useState(false);
  const [materialConfirmed, setMaterialConfirmed] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const availableProfiles = useMemo(
    () => printer?.profiles.filter((profile) => profile.available) ?? [],
    [printer?.profiles],
  );

  useEffect(() => {
    if (
      profileId === "" ||
      !availableProfiles.some((profile) => profile.profileId === profileId)
    ) {
      setProfileId(availableProfiles[0]?.profileId ?? "");
    }
  }, [availableProfiles, profileId]);

  useEffect(() => {
    if (
      selectedSourceId === "" ||
      !printer?.sources.some((source) => source.artifactId === selectedSourceId)
    ) {
      setSelectedSourceId(printer?.sources.at(-1)?.artifactId ?? "");
    }
  }, [printer?.sources, selectedSourceId]);

  useEffect(() => {
    if (
      startIntent !== undefined &&
      !printer?.gcodeArtifacts.some(
        (artifact) => artifact.artifactId === startIntent.artifactId,
      )
    ) {
      setStartIntent(undefined);
      setPlateClear(false);
      setMaterialConfirmed(false);
    }
  }, [printer?.gcodeArtifacts, startIntent]);

  const stage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (file === null) return;
    if (await onStage(file)) {
      setFile(null);
      if (fileInput.current !== null) fileInput.current.value = "";
    }
  };

  if (printer === null) {
    return (
      <section className="fabric-panel fabric-printer-panel" aria-busy="true">
        <p className="eyebrow">{t("printer.eyebrow")}</p>
        <h2>{t("printer.title")}</h2>
        <p>{t("printer.loading")}</p>
      </section>
    );
  }

  const statusKey = `printer.state.${printer.state}` as const;
  const locked = printer.state === "current_print_locked";
  const selectedSource = printer.sources.find(
    (source) => source.artifactId === selectedSourceId,
  );
  const selectedProfile = printer.profiles.find(
    (profile) => profile.profileId === profileId,
  );
  const lockReasonKeys: Record<
    NonNullable<FabricPrinterSnapshot["operations"]["lockReasonCode"]>,
    FabricMessageKey
  > = {
    current_print: "printer.lockReason.currentPrint",
    monitoring_not_configured: "printer.lockReason.monitoringNotConfigured",
    remote_writes_disabled: "printer.lockReason.remoteWritesDisabled",
    not_standby: "printer.lockReason.notStandby",
  };
  const lockReasonKey =
    printer.operations.lockReasonCode === undefined
      ? undefined
      : lockReasonKeys[printer.operations.lockReasonCode];

  return (
    <section
      className={`fabric-panel fabric-printer-panel is-${printer.state}`}
      id="three-d-printer"
      aria-labelledby="printer-title"
    >
      <div className="fabric-printer-heading">
        <div>
          <p className="eyebrow">{t("printer.eyebrow")}</p>
          <h2 id="printer-title">{t("printer.title")}</h2>
        </div>
        <span className={`fabric-printer-state is-${printer.state}`}>
          {t(statusKey)}
        </span>
      </div>

      <div className="fabric-printer-identity">
        <div>
          <strong>{printer.model}</strong>
          <span>{printer.address}</span>
        </div>
        <div>
          <small>{t("printer.transport")}</small>
          <span>
            {printer.transport === "Not verified"
              ? t("printer.transportUnverified")
              : printer.transport}
          </span>
        </div>
        {printer.nozzle !== undefined && (
          <div>
            <small>{t("printer.nozzle")}</small>
            <span>
              {formatTemperature(printer.nozzle.actualCelsius)} /{" "}
              {formatTemperature(printer.nozzle.targetCelsius)}
            </span>
          </div>
        )}
        {printer.bed !== undefined && (
          <div>
            <small>{t("printer.bed")}</small>
            <span>
              {formatTemperature(printer.bed.actualCelsius)} /{" "}
              {formatTemperature(printer.bed.targetCelsius)}
            </span>
          </div>
        )}
      </div>

      {printer.currentJob !== undefined && (
        <div className="fabric-printer-current-job">
          <strong>{t("printer.currentJob")}</strong>
          <span>{printer.currentJob.filename}</span>
          {printer.currentJob.progressPercent !== undefined && (
            <progress
              max={100}
              value={printer.currentJob.progressPercent}
              aria-label={t("printer.progress")}
            />
          )}
        </div>
      )}

      <div
        className={`fabric-printer-safety ${locked ? "is-locked" : ""}`}
        role="status"
      >
        <span aria-hidden="true">{locked ? "🔒" : "✓"}</span>
        <div>
          <strong>
            {t(
              locked
                ? "printer.currentPrintProtected"
                : "printer.separateActions",
            )}
          </strong>
          <small>
            {lockReasonKey === undefined
              ? t("printer.readyHelp")
              : t(lockReasonKey, { state: t(statusKey) })}
          </small>
        </div>
        <FabricInfoDisclosure label={t("common.moreInfo")}>
          <p>{t("printer.safetyHelp")}</p>
          <p>{t("printer.noFanout")}</p>
        </FabricInfoDisclosure>
      </div>

      {locked && (
        <button
          className="fabric-printer-verify"
          type="button"
          disabled={!canManage || busy || !printer.operations.verifyIdle}
          onClick={() => void onVerifyIdle()}
        >
          {t("printer.verifyIdle")}
          <small>{t("printer.verifyIdleHelp")}</small>
        </button>
      )}

      <ol className="fabric-printer-workflow">
        <li>
          <div className="fabric-printer-step-heading">
            <span>1</span>
            <div>
              <strong>{t("printer.stageTitle")}</strong>
              <small>{t("printer.stageHelp")}</small>
            </div>
          </div>
          <form className="fabric-printer-file-form" onSubmit={stage}>
            <input
              ref={fileInput}
              type="file"
              accept=".stl,.3mf,model/stl,model/3mf"
              aria-label={t("printer.chooseModel")}
              disabled={!canManage || busy || !printer.operations.stageSource}
              onChange={(event) => setFile(event.target.files?.item(0) ?? null)}
            />
            <button
              type="submit"
              disabled={
                !canManage ||
                busy ||
                !printer.operations.stageSource ||
                file === null
              }
            >
              {t("printer.addModel")}
            </button>
          </form>
          {printer.sources.length > 0 && (
            <label className="fabric-printer-select">
              <span>{t("printer.model")}</span>
              <select
                value={selectedSourceId}
                disabled={busy}
                onChange={(event) => setSelectedSourceId(event.target.value)}
              >
                {printer.sources.map((source) => (
                  <option value={source.artifactId} key={source.artifactId}>
                    {source.fileName} · {formatBytes(source.sizeBytes)}
                  </option>
                ))}
              </select>
            </label>
          )}
        </li>

        <li>
          <div className="fabric-printer-step-heading">
            <span>2</span>
            <div>
              <strong>{t("printer.sliceTitle")}</strong>
              <small>{t("printer.sliceHelp")}</small>
            </div>
          </div>
          <div className="fabric-printer-slice-controls">
            <label className="fabric-printer-select">
              <span>{t("printer.profile")}</span>
              <select
                value={profileId}
                disabled={busy || availableProfiles.length === 0}
                onChange={(event) => setProfileId(event.target.value)}
              >
                {availableProfiles.length === 0 && (
                  <option value="">{t("printer.noProfile")}</option>
                )}
                {availableProfiles.map((profile) => (
                  <option value={profile.profileId} key={profile.profileId}>
                    {profile.displayName}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={
                !canManage ||
                busy ||
                !printer.operations.slice ||
                selectedSource === undefined ||
                selectedProfile === undefined
              }
              onClick={() => void onSlice(selectedSourceId, profileId)}
            >
              {t("printer.prepareGcode")}
            </button>
          </div>
        </li>

        <li>
          <div className="fabric-printer-step-heading">
            <span>3</span>
            <div>
              <strong>{t("printer.outputTitle")}</strong>
              <small>{t("printer.outputHelp")}</small>
            </div>
          </div>
          {printer.gcodeArtifacts.length === 0 ? (
            <p className="fabric-printer-empty">{t("printer.noGcode")}</p>
          ) : (
            <ul className="fabric-printer-artifacts">
              {printer.gcodeArtifacts.map((artifact) => (
                <li key={artifact.artifactId}>
                  <div>
                    <strong>{artifact.fileName}</strong>
                    <small>
                      {formatBytes(artifact.sizeBytes)} · SHA-256{" "}
                      {artifact.sha256.slice(0, 12)}…
                    </small>
                    <span>
                      {artifact.remoteFileName === undefined
                        ? t("printer.localOnly")
                        : t("printer.uploadedAs", {
                            name: artifact.remoteFileName,
                          })}
                    </span>
                  </div>
                  <div className="fabric-printer-artifact-actions">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void onDownload(artifact)}
                    >
                      {t("printer.download")}
                    </button>
                    {artifact.remoteFileName === undefined && (
                      <button
                        type="button"
                        disabled={
                          !canManage || busy || !printer.operations.upload
                        }
                        onClick={() => void onUpload(artifact.artifactId)}
                      >
                        {t("printer.uploadOnly")}
                      </button>
                    )}
                    {artifact.remoteFileName !== undefined && (
                      <button
                        className="fabric-printer-start-button"
                        type="button"
                        disabled={
                          !canManage || busy || !printer.operations.start
                        }
                        onClick={() => {
                          void onPrepareStart(artifact.artifactId).then(
                            (intent) => {
                              if (intent === undefined) return;
                              setStartIntent(intent);
                              setPlateClear(false);
                              setMaterialConfirmed(false);
                            },
                          );
                        }}
                      >
                        {t("printer.startPrint")}
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </li>
      </ol>

      {startIntent !== undefined && (
        <section
          className="fabric-printer-start-confirmation"
          aria-labelledby="printer-confirm-title"
        >
          <h3 id="printer-confirm-title">{t("printer.confirmTitle")}</h3>
          <p>{startIntent.remoteFileName}</p>
          <label>
            <input
              type="checkbox"
              checked={plateClear}
              disabled={busy}
              onChange={(event) => setPlateClear(event.target.checked)}
            />
            <span>{t("printer.confirmPlate")}</span>
          </label>
          <label>
            <input
              type="checkbox"
              checked={materialConfirmed}
              disabled={busy}
              onChange={(event) => setMaterialConfirmed(event.target.checked)}
            />
            <span>{t("printer.confirmMaterial")}</span>
          </label>
          <div>
            <button
              type="button"
              disabled={busy}
              onClick={() => setStartIntent(undefined)}
            >
              {t("printer.cancel")}
            </button>
            <button
              className="fabric-printer-confirm-start"
              type="button"
              disabled={busy || !plateClear || !materialConfirmed}
              onClick={() => {
                void onStart(
                  startIntent.artifactId,
                  startIntent.confirmationToken,
                ).then((started) => {
                  if (started) setStartIntent(undefined);
                });
              }}
            >
              {t("printer.confirmStart")}
            </button>
          </div>
        </section>
      )}
    </section>
  );
}

const formatBytes = (bytes: number): string =>
  bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

const formatTemperature = (value: number): string => `${Math.round(value)} °C`;
