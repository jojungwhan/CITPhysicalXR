import { useMemo } from "react";

import type {
  FabricDiscoveryCandidate,
  SpheroBoltSelection,
} from "./fabric-client.js";
import type { FabricTranslate } from "./fabric-i18n.js";
import {
  selectableSpheroCandidates,
  selectableSpheroOllieCandidates,
  spheroOllieSelection,
  spheroSelection,
  type SpheroVariant,
} from "./fabric-sphero-bolt.js";

export function FabricSpheroSetup({
  candidates,
  variant = "bolt",
  busy,
  canConnect,
  onConnect,
  t,
}: {
  candidates: FabricDiscoveryCandidate[];
  variant?: SpheroVariant;
  busy: boolean;
  canConnect: boolean;
  onConnect: (robots: SpheroBoltSelection[]) => void;
  t: FabricTranslate;
}) {
  const selectable = useMemo(
    () =>
      variant === "ollie"
        ? selectableSpheroOllieCandidates(candidates)
        : selectableSpheroCandidates(candidates),
    [candidates, variant],
  );
  const prefix = variant === "ollie" ? "ollie" : "sphero";

  return (
    <div className="fabric-sphero-setup">
      <strong>{t(`${prefix}.setup` as "sphero.setup")}</strong>
      {selectable.length === 0 ? (
        <small>{t(`${prefix}.noneVisible` as "sphero.noneVisible")}</small>
      ) : (
        <div className="fabric-sphero-candidate-list">
          {selectable.map((candidate) => (
            <button
              className="fabric-connect-device fabric-sphero-candidate"
              type="button"
              key={candidate.candidateId}
              disabled={!canConnect || busy}
              onClick={() => {
                const selection =
                  variant === "ollie"
                    ? spheroOllieSelection(candidate)
                    : spheroSelection(candidate);
                if (selection !== undefined) onConnect([selection]);
              }}
            >
              <span>
                <strong>{candidate.displayName}</strong>
                <small>
                  {t(`${prefix}.capabilities` as "sphero.capabilities")}
                  {candidate.signalPercent === undefined
                    ? ""
                    : ` · ${t("discovery.signal", { percent: candidate.signalPercent })}`}
                </small>
              </span>
              <b>
                {busy
                  ? t(`${prefix}.connecting` as "sphero.connecting")
                  : t(`${prefix}.connectRobot` as "sphero.connectRobot")}
              </b>
            </button>
          ))}
        </div>
      )}
      <details className="fabric-setup-tips">
        <summary>{t("common.moreInfo")}</summary>
        <ol>
          <li>{t(`${prefix}.wake` as "sphero.wake")}</li>
          <li>{t(`${prefix}.closeApps` as "sphero.closeApps")}</li>
          <li>{t(`${prefix}.noPairing` as "sphero.noPairing")}</li>
        </ol>
        <small>{t(`${prefix}.connectSafety` as "sphero.connectSafety")}</small>
      </details>
    </div>
  );
}
