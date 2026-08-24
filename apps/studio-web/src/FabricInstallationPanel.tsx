import type { FabricInstallationInfo } from "./fabric-client.js";
import {
  formatInstallationSize,
  selectWindowsInstallationArtifact,
} from "./fabric-installation.js";
import type { FabricTranslate } from "./fabric-i18n.js";
import type { Locale } from "./i18n.js";

export function FabricInstallationPanel({
  info,
  locale,
  busy,
  canDownload,
  onDownload,
  onDownloadSiteTemplate,
  t,
}: {
  info: FabricInstallationInfo | null;
  locale: Locale;
  busy: boolean;
  canDownload: boolean;
  onDownload: () => void;
  onDownloadSiteTemplate: () => void;
  t: FabricTranslate;
}) {
  const artifact = selectWindowsInstallationArtifact(info);
  const revision = info?.revision?.slice(0, 12);
  const steps = [
    {
      title: t("installation.step1.title"),
      body: t("installation.step1.body"),
    },
    {
      title: t("installation.step2.title"),
      body: t("installation.step2.body"),
    },
    {
      title: t("installation.step3.title"),
      body: t("installation.step3.body"),
    },
    {
      title: t("installation.step4.title"),
      body: t("installation.step4.body"),
    },
  ];

  return (
    <section
      className="fabric-panel fabric-installation-panel"
      id="install-another-pc"
      aria-labelledby="install-another-pc-title"
    >
      <div className="fabric-installation-heading">
        <div>
          <p className="eyebrow">{t("installation.eyebrow")}</p>
          <h2 id="install-another-pc-title">{t("installation.title")}</h2>
          <p className="fabric-panel-intro">{t("installation.intro")}</p>
        </div>
        <span className="fabric-installation-platform">
          {t("installation.platform")}
        </span>
      </div>

      <div className="fabric-installation-network" role="note">
        <strong>{t("installation.internetTitle")}</strong>
        <p>{t("installation.internetBody")}</p>
        <small>{t("installation.noCloud")}</small>
      </div>

      <ol className="fabric-installation-steps">
        {steps.map((step, index) => (
          <li key={step.title}>
            <span>{index + 1}</span>
            <div>
              <strong>{step.title}</strong>
              <p>{step.body}</p>
            </div>
          </li>
        ))}
      </ol>

      {info === null ? (
        <div className="fabric-installation-unavailable" role="status">
          <strong>
            {canDownload
              ? t("installation.loadingTitle")
              : t("installation.permission")}
          </strong>
          <p>
            {canDownload
              ? t("installation.loadingBody")
              : t("installation.unavailableBody")}
          </p>
        </div>
      ) : artifact === undefined ? (
        <div className="fabric-installation-unavailable" role="status">
          <strong>{t("installation.unavailableTitle")}</strong>
          <p>{t("installation.unavailableBody")}</p>
          <details>
            <summary>{t("installation.technical")}</summary>
            <code>pnpm release:windows:bundle</code>
          </details>
        </div>
      ) : (
        <div className="fabric-installation-package">
          <div className="fabric-installation-package-copy">
            <p className="eyebrow">{t("installation.packageEyebrow")}</p>
            <h3>{artifact.fileName}</h3>
            <dl>
              <div>
                <dt>{t("installation.version")}</dt>
                <dd>{info?.version ?? "—"}</dd>
              </div>
              <div>
                <dt>{t("installation.revision")}</dt>
                <dd>{revision ?? "—"}</dd>
              </div>
              <div>
                <dt>{t("installation.size")}</dt>
                <dd>{formatInstallationSize(artifact.sizeBytes, locale)}</dd>
              </div>
            </dl>
            <div className="fabric-installation-checksum">
              <span>{t("installation.checksum")}</span>
              <code>{artifact.sha256}</code>
            </div>
          </div>
          <div className="fabric-installation-actions">
            <button
              className="fabric-primary-action"
              type="button"
              disabled={busy || !canDownload}
              onClick={onDownload}
            >
              {t("installation.download")}
              <small>{t("installation.downloadHelp")}</small>
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={onDownloadSiteTemplate}
            >
              {t("installation.siteTemplate")}
            </button>
            <small>{t("installation.siteTemplateHelp")}</small>
            {!canDownload && (
              <small className="fabric-installation-permission">
                {t("installation.permission")}
              </small>
            )}
          </div>
        </div>
      )}

      <div className="fabric-installation-boundaries">
        <div>
          <strong>{t("installation.includedTitle")}</strong>
          <p>{t("installation.includedBody")}</p>
        </div>
        <div>
          <strong>{t("installation.excludedTitle")}</strong>
          <p>{t("installation.excludedBody")}</p>
        </div>
      </div>
    </section>
  );
}
