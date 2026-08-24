import { useEffect, useMemo, useState } from "react";

import type {
  FabricDiscoveryCandidate,
  SpheroBoltSelection,
} from "./fabric-client.js";
import type { FabricTranslate } from "./fabric-i18n.js";
import {
  selectableSpheroCandidates,
  spheroSelection,
} from "./fabric-sphero-bolt.js";

export function FabricSpheroSetup({
  candidates,
  busy,
  canConnect,
  onConnect,
  t,
}: {
  candidates: FabricDiscoveryCandidate[];
  busy: boolean;
  canConnect: boolean;
  onConnect: (robots: SpheroBoltSelection[]) => void;
  t: FabricTranslate;
}) {
  const selectable = useMemo(
    () => selectableSpheroCandidates(candidates),
    [candidates],
  );
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    const visible = new Set(
      selectable.map((candidate) => candidate.candidateId),
    );
    setSelected((current) => current.filter((value) => visible.has(value)));
  }, [selectable]);

  return (
    <div className="fabric-sphero-setup">
      <strong>{t("sphero.setup")}</strong>
      <ol>
        <li>{t("sphero.wake")}</li>
        <li>{t("sphero.closeApps")}</li>
        <li>{t("sphero.noPairing")}</li>
      </ol>
      {selectable.length === 0 ? (
        <small>{t("sphero.noneVisible")}</small>
      ) : (
        <fieldset>
          <legend>{t("sphero.selectExact")}</legend>
          {selectable.map((candidate) => (
            <label key={candidate.candidateId}>
              <input
                type="checkbox"
                checked={selected.includes(candidate.candidateId)}
                onChange={(event) =>
                  setSelected((current) =>
                    event.target.checked
                      ? [...current, candidate.candidateId].slice(0, 4)
                      : current.filter(
                          (value) => value !== candidate.candidateId,
                        ),
                  )
                }
              />
              <span>
                <strong>{candidate.displayName}</strong>
                <small>
                  {t("sphero.boltCapabilities")}
                  {candidate.signalPercent === undefined
                    ? ""
                    : ` · ${t("discovery.signal", { percent: candidate.signalPercent })}`}
                </small>
              </span>
            </label>
          ))}
        </fieldset>
      )}
      <button
        className="fabric-connect-device"
        type="button"
        disabled={!canConnect || busy || selected.length === 0}
        onClick={() =>
          onConnect(
            selected.flatMap((candidateId) => {
              const candidate = selectable.find(
                (item) => item.candidateId === candidateId,
              );
              const selection =
                candidate === undefined
                  ? undefined
                  : spheroSelection(candidate);
              return selection === undefined ? [] : [selection];
            }),
          )
        }
      >
        {busy ? t("sphero.connecting") : t("sphero.connectSelected")}
      </button>
      <small>{t("sphero.connectSafety")}</small>
    </div>
  );
}
