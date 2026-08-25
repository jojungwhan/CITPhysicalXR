import { useEffect, useMemo, useState } from "react";

import type {
  FabricDiscoveryCandidate,
  WonderRobotSelection,
} from "./fabric-client.js";
import type { FabricTranslate } from "./fabric-i18n.js";
import {
  selectableWonderCandidates,
  wonderCandidateModel,
  wonderSelection,
} from "./fabric-wonder-workshop.js";

export function FabricWonderWorkshopSetup({
  candidates,
  busy,
  canConnect,
  onConnect,
  t,
}: {
  candidates: FabricDiscoveryCandidate[];
  busy: boolean;
  canConnect: boolean;
  onConnect: (robots: WonderRobotSelection[]) => void;
  t: FabricTranslate;
}) {
  const selectable = useMemo(
    () => selectableWonderCandidates(candidates),
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
    <div className="fabric-wonder-setup">
      <strong>{t("wonder.setup")}</strong>
      <details className="fabric-setup-tips">
        <summary>{t("common.moreInfo")}</summary>
        <p>{t("wonder.setupHelp")}</p>
        <small>{t("wonder.connectSafety")}</small>
      </details>
      {selectable.length === 0 ? (
        <small>{t("wonder.noneVisible")}</small>
      ) : (
        <fieldset>
          <legend>{t("wonder.selectExact")}</legend>
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
                  {wonderCandidateModel(candidate) === "dash"
                    ? t("wonder.dash")
                    : t("wonder.dot")}
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
                  : wonderSelection(candidate);
              return selection === undefined ? [] : [selection];
            }),
          )
        }
      >
        {busy ? t("wonder.connecting") : t("wonder.connectSelected")}
      </button>
    </div>
  );
}
