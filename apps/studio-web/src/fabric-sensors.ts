import type { StoredFabricEvent } from "./fabric-client.js";

export interface FabricSensorValue {
  label: string;
  value: string;
}

export interface FabricSensorReading {
  key: string;
  sourceNodeId: string;
  topic: string;
  observedAt: string;
  values: FabricSensorValue[];
}

const SENSOR_PREFIXES = ["sensor.", "telemetry.", "biosignal.", "mindwave."];
const HIDDEN_PAYLOAD_KEYS = new Set([
  "audio",
  "camera",
  "credentials",
  "image",
  "token",
  "video",
]);

export const latestSensorReadings = (
  events: readonly StoredFabricEvent[],
  limit = 16,
): FabricSensorReading[] => {
  const latest = new Map<string, FabricSensorReading>();
  for (const stored of [...events].reverse()) {
    const event = stored.event;
    if (!SENSOR_PREFIXES.some((prefix) => event.topic.startsWith(prefix))) {
      continue;
    }
    const key = `${event.sourceNodeId}:${event.topic}`;
    if (latest.has(key)) continue;
    latest.set(key, {
      key,
      sourceNodeId: event.sourceNodeId,
      topic: event.topic,
      observedAt: event.timestamp,
      values: sensorValues(event.payload),
    });
    if (latest.size >= limit) break;
  }
  return [...latest.values()];
};

const sensorValues = (payload: unknown): FabricSensorValue[] => {
  if (
    typeof payload !== "object" ||
    payload === null ||
    Array.isArray(payload)
  ) {
    return [{ label: "value", value: displayValue(payload) }];
  }
  const object = payload as Record<string, unknown>;
  const unit = typeof object["unit"] === "string" ? object["unit"] : undefined;
  const values = Object.entries(object)
    .filter(
      ([key, value]) =>
        key !== "unit" &&
        !HIDDEN_PAYLOAD_KEYS.has(key.toLowerCase()) &&
        ["boolean", "number", "string"].includes(typeof value),
    )
    .slice(0, 6)
    .map(([label, value]) => ({
      label: humanize(label),
      value: `${displayValue(value)}${unit === undefined ? "" : ` ${unit}`}`,
    }));
  return values.length === 0 ? [{ label: "value", value: "Observed" }] : values;
};

const displayValue = (value: unknown): string => {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === "boolean") return value ? "On" : "Off";
  if (typeof value === "string") return value.slice(0, 80);
  return "Observed";
};

const humanize = (value: string): string =>
  value
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replaceAll("_", " ")
    .replace(/^./, (first) => first.toUpperCase());
