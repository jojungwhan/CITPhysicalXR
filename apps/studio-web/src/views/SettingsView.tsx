import { useCallback, useEffect, useState } from "react";

import { LOCALES, type Locale, type Translate } from "../i18n.js";
import type {
  HealthView,
  Identity,
  RetentionView,
  RuntimeClient,
} from "../runtime-client.js";

/**
 * UI 11.5 language, FR-084 retention, and what runtime this is.
 *
 * Retention is an instructor's decision because it decides what is deleted from
 * a shared machine. A student can read it -- knowing how long their own
 * recordings survive is not a privilege.
 */
export function SettingsView({
  client,
  identity,
  health,
  locale,
  onLocale,
  t,
  run,
  busy,
}: {
  client: RuntimeClient;
  identity: Identity;
  health: HealthView | null;
  locale: Locale;
  onLocale: (locale: Locale) => void;
  t: Translate;
  run: (work: () => Promise<void>) => Promise<void>;
  busy: boolean;
}) {
  const [retention, setRetention] = useState<RetentionView>({
    maxRecordings: 50,
    retentionDays: 30,
  });
  const [saved, setSaved] = useState(false);

  const refresh = useCallback(async () => {
    setRetention((await client.recordings()).policy);
  }, [client]);

  useEffect(() => {
    void run(refresh);
  }, [refresh, run]);

  const save = () =>
    run(async () => {
      await client.setRetention(retention);
      setSaved(true);
    });

  return (
    <>
      <section aria-labelledby="settings-heading">
        <h2 id="settings-heading">{t("settings.heading")}</h2>

        <h3>{t("settings.language")}</h3>
        <div className="row">
          {LOCALES.map((option) => (
            <button
              key={option}
              type="button"
              className={option === locale ? "chip current" : "chip"}
              onClick={() => onLocale(option)}
              aria-pressed={option === locale}
            >
              {option === "en" ? t("settings.english") : t("settings.korean")}
            </button>
          ))}
        </div>
      </section>

      <section aria-labelledby="retention-heading">
        <h2 id="retention-heading">{t("settings.retention")}</h2>
        <p className="muted">{t("settings.retentionExplain")}</p>
        <div className="row">
          <label>
            <span>{t("settings.maxRecordings")}</span>
            <input
              type="number"
              min={1}
              max={10000}
              value={retention.maxRecordings}
              disabled={identity.role !== "instructor"}
              onChange={(event) =>
                setRetention((current) => ({
                  ...current,
                  maxRecordings: Number(event.target.value),
                }))
              }
            />
          </label>
          <label>
            <span>{t("settings.retentionDays")}</span>
            <input
              type="number"
              min={1}
              max={3650}
              value={retention.retentionDays}
              disabled={identity.role !== "instructor"}
              onChange={(event) =>
                setRetention((current) => ({
                  ...current,
                  retentionDays: Number(event.target.value),
                }))
              }
            />
          </label>
          {identity.role === "instructor" && (
            <button type="button" onClick={save} disabled={busy}>
              {t("settings.saveRetention")}
            </button>
          )}
        </div>
        {saved && <div className="notice ok">{t("projects.saved")}</div>}
      </section>

      <section aria-labelledby="runtime-heading">
        <h2 id="runtime-heading">{t("runtime.heading")}</h2>
        {health === null ? (
          <p className="muted">{t("runtime.unreachable")}</p>
        ) : (
          <dl className="facts">
            <div>
              <dt>{t("runtime.id")}</dt>
              <dd>{health.runtimeId}</dd>
            </div>
            <div>
              <dt>{t("runtime.protocol")}</dt>
              <dd>v{health.protocolVersion}</dd>
            </div>
            <div>
              <dt>{t("runtime.mode")}</dt>
              <dd>{health.executionMode}</dd>
            </div>
            <div>
              <dt>{t("runtime.physical")}</dt>
              <dd>
                {health.physicalEnabled
                  ? t("runtime.enabled")
                  : t("runtime.disabled")}
              </dd>
            </div>
          </dl>
        )}
      </section>
    </>
  );
}
