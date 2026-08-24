import { useState } from "react";

import type { FabricDiscoveryCandidate } from "./fabric-client.js";
import type { FabricTranslate } from "./fabric-i18n.js";

export function FabricMatterSetup({
  candidates,
  commissioning,
  configuringWifi,
  canConnect,
  connected,
  onCommission,
  onConfigureWifi,
  t,
}: {
  candidates: FabricDiscoveryCandidate[];
  commissioning: boolean;
  configuringWifi: boolean;
  canConnect: boolean;
  connected: boolean;
  onCommission: (setupCode: string) => Promise<boolean>;
  onConfigureWifi: (ssid: string, password: string) => Promise<boolean>;
  t: FabricTranslate;
}) {
  const [setupCode, setSetupCode] = useState("");
  const [ssid, setSsid] = useState("");
  const [wifiPassword, setWifiPassword] = useState("");
  const wifiCandidate = candidates.find(
    (candidate) => candidate.candidateId === "matter-controller-wifi",
  );
  const wifiReady = wifiCandidate?.status === "ready";
  const nearbyDevices = candidates.filter(
    (candidate) =>
      candidate.candidateId.startsWith("matter-") &&
      candidate.candidateId !== "matter-controller-wifi" &&
      candidate.status === "found",
  );
  const busy = commissioning || configuringWifi;

  const configureWifi = async () => {
    if (await onConfigureWifi(ssid.trim(), wifiPassword)) {
      setWifiPassword("");
    }
  };

  const commission = async () => {
    const normalized = setupCode.trim();
    if (await onCommission(normalized)) setSetupCode("");
  };

  const setupStages = (
    <>
      <p>{t("matter.help")}</p>

      <section
        className={`fabric-matter-stage ${wifiReady ? "is-ready" : "is-required"}`}
        aria-labelledby="matter-wifi-stage"
      >
        <header>
          <span aria-hidden="true">1</span>
          <div>
            <strong id="matter-wifi-stage">{t("matter.wifi.title")}</strong>
            <small>
              {wifiReady
                ? t("matter.wifi.ready")
                : wifiCandidate
                  ? t("matter.wifi.required")
                  : t("matter.wifi.scanFirst")}
            </small>
          </div>
          <b>{wifiReady ? t("matter.ready") : t("matter.required")}</b>
        </header>
        {!wifiReady && wifiCandidate && (
          <div className="fabric-matter-wifi-form">
            <label>
              {t("matter.wifi.ssid")}
              <input
                type="text"
                value={ssid}
                autoComplete="off"
                spellCheck={false}
                placeholder={t("matter.wifi.ssidPlaceholder")}
                onChange={(event) => setSsid(event.target.value)}
              />
            </label>
            <label>
              {t("matter.wifi.password")}
              <input
                type="password"
                value={wifiPassword}
                autoComplete="off"
                spellCheck={false}
                placeholder={t("matter.wifi.passwordPlaceholder")}
                onChange={(event) => setWifiPassword(event.target.value)}
              />
            </label>
            <button
              className="fabric-connect-device"
              type="button"
              disabled={
                !canConnect ||
                busy ||
                ssid.trim().length === 0 ||
                wifiPassword.length < 8
              }
              onClick={() => void configureWifi()}
            >
              {configuringWifi
                ? t("matter.wifi.saving")
                : t("matter.wifi.save")}
            </button>
            <small>{t("matter.wifi.memory")}</small>
          </div>
        )}
      </section>

      <section
        className="fabric-matter-stage"
        aria-labelledby="matter-device-stage"
      >
        <header>
          <span aria-hidden="true">2</span>
          <div>
            <strong id="matter-device-stage">{t("matter.device.title")}</strong>
            <small>{t("matter.device.help")}</small>
          </div>
          <b>
            {nearbyDevices.length > 0
              ? t("matter.device.found", { count: nearbyDevices.length })
              : t("matter.device.waiting")}
          </b>
        </header>
        {nearbyDevices.length > 0 && (
          <ul className="fabric-matter-nearby">
            {nearbyDevices.map((candidate) => (
              <li key={candidate.candidateId}>{candidate.displayName}</li>
            ))}
          </ul>
        )}
      </section>

      <section
        className={`fabric-matter-stage ${wifiReady ? "" : "is-locked"}`}
        aria-labelledby="matter-code-stage"
      >
        <header>
          <span aria-hidden="true">3</span>
          <div>
            <strong id="matter-code-stage">{t("matter.code.title")}</strong>
            <small>
              {wifiReady ? t("matter.code.help") : t("matter.code.locked")}
            </small>
          </div>
        </header>
        <label>
          {t("matter.code")}
          <input
            type="text"
            value={setupCode}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            placeholder={t("matter.placeholder")}
            disabled={!wifiReady}
            onChange={(event) => setSetupCode(event.target.value)}
          />
        </label>
        <button
          className="fabric-connect-device"
          type="button"
          disabled={
            !canConnect || busy || !wifiReady || setupCode.trim().length < 11
          }
          onClick={() => void commission()}
        >
          {commissioning
            ? t("matter.adding")
            : connected
              ? t("matter.addAnotherButton")
              : t("matter.addLocally")}
        </button>
        <small>{t("matter.memory")}</small>
      </section>

      <details className="fabric-advanced-setup">
        <summary>{t("matter.tapo.title")}</summary>
        <p>{t("matter.tapo.support")}</p>
        <ol>
          <li>{t("matter.tapo.reset")}</li>
          <li>{t("matter.tapo.window")}</li>
          <li>{t("matter.tapo.network")}</li>
          <li>{t("matter.tapo.code")}</li>
        </ol>
        <small>{t("matter.tapo.energy")}</small>
      </details>
    </>
  );

  return connected ? (
    <details className="fabric-matter-setup fabric-add-another-device">
      <summary>{t("matter.addAnother")}</summary>
      {setupStages}
    </details>
  ) : (
    <div className="fabric-matter-setup">
      <strong>{t("matter.add")}</strong>
      {setupStages}
    </div>
  );
}
