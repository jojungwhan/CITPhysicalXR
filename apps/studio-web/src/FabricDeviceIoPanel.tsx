import type { IntegrationNode } from "@citxr/protocol";

import {
  fabricCapabilityName,
  fabricConnectionState,
  fabricFormatTime,
  fabricHealthState,
  type FabricTranslate,
} from "./fabric-i18n.js";
import type { FabricSensorReading } from "./fabric-sensors.js";
import type { Locale } from "./i18n.js";

export function FabricDeviceIoPanel({
  nodes,
  readings,
  locale,
  t,
}: {
  nodes: IntegrationNode[];
  readings: FabricSensorReading[];
  locale: Locale;
  t: FabricTranslate;
}) {
  if (nodes.length === 0) return null;
  const liveSummary = readings
    .filter((reading) =>
      nodes.some((node) => node.nodeId === reading.sourceNodeId),
    )
    .flatMap((reading) => reading.values)
    .slice(0, 4)
    .map((value) => `${value.label}: ${value.value}`)
    .join(" · ");

  return (
    <details className="fabric-inline-device-io">
      <summary className="fabric-inline-device-io-heading">
        <strong>{t("deviceIo.title")}</strong>
        <span>
          {liveSummary || nodes.map((node) => node.displayName).join(" · ")}
        </span>
        <i aria-hidden="true">⌄</i>
      </summary>
      <div className="fabric-inline-device-io-content">
        <div className="fabric-inline-device-io-list">
          {nodes.map((node) => {
            const nodeReadings = readings
              .filter((reading) => reading.sourceNodeId === node.nodeId)
              .slice(0, 3);
            return (
              <article className="fabric-inline-device-node" key={node.nodeId}>
                <header>
                  <div>
                    <strong>{node.displayName}</strong>
                    <small>{node.nodeId}</small>
                  </div>
                  <span>
                    {fabricConnectionState(node, t)} ·{" "}
                    {fabricHealthState(node.healthState, t)}
                  </span>
                </header>
                <div className="fabric-inline-io-columns">
                  <InlineCapabilityList
                    kind="input"
                    label={t("deviceIo.inputs")}
                    capabilities={node.publishedCapabilities.map(
                      (capability) => capability.name,
                    )}
                    locale={locale}
                    emptyLabel={t("nodes.none")}
                  />
                  <InlineCapabilityList
                    kind="output"
                    label={t("deviceIo.outputs")}
                    capabilities={node.consumedCapabilities.map(
                      (capability) => capability.name,
                    )}
                    locale={locale}
                    emptyLabel={t("nodes.none")}
                  />
                </div>
                {nodeReadings.length > 0 && (
                  <div className="fabric-inline-readings">
                    <strong>{t("deviceIo.live")}</strong>
                    {nodeReadings.map((reading) => (
                      <div key={reading.key}>
                        <span>
                          {fabricCapabilityName(reading.topic, locale)} ·{" "}
                          {fabricFormatTime(reading.observedAt, locale)}
                        </span>
                        <p>
                          {reading.values.map((value) => (
                            <span key={value.label}>
                              {value.label}: <strong>{value.value}</strong>
                            </span>
                          ))}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      </div>
    </details>
  );
}

function InlineCapabilityList({
  kind,
  label,
  capabilities,
  locale,
  emptyLabel,
}: {
  kind: "input" | "output";
  label: string;
  capabilities: string[];
  locale: Locale;
  emptyLabel: string;
}) {
  return (
    <div className={`fabric-inline-capabilities is-${kind}`}>
      <strong>{label}</strong>
      <div>
        {capabilities.length === 0 ? (
          <span>{emptyLabel}</span>
        ) : (
          capabilities.map((capability) => (
            <span title={capability} key={capability}>
              {fabricCapabilityName(capability, locale)}
            </span>
          ))
        )}
      </div>
    </div>
  );
}
