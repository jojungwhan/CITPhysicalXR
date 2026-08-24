import type { StoredFabricEvent } from "./fabric-client.js";

export const LEAP_GESTURE_CAPABILITY = "interaction.gesture.velocity";

export interface LeapVector3 {
  x: number;
  y: number;
  z: number;
}

export interface LeapHandSample {
  handId: number;
  handedness: "left" | "right";
  visibleTimeSeconds: number;
  palmMillimeters: LeapVector3;
  velocityMillimetersPerSecond: LeapVector3;
  direction: LeapVector3;
  palmNormal: LeapVector3;
  pinchStrength: number;
  grabStrength: number;
  pinchDistanceMillimeters: number;
  yawDegrees: number;
}

export interface LeapTrackingReading {
  sourceNodeId: string;
  observedAt: string;
  streamSequence: number;
  tracking: boolean;
  state: string;
  reason: string;
  confidence: number;
  sensorFrameRateHertz?: number;
  totalHandCount: number;
  serviceConnected: boolean;
  devicePresent: boolean;
  hand?: LeapHandSample;
  command: {
    forwardMetersPerSecond: number;
    rightMetersPerSecond: number;
    clockwiseRadiansPerSecond: number;
  };
}

export interface LeapHandGeometry {
  xPercent: number;
  yPercent: number;
  rotationDegrees: number;
  fingerExtension: number;
  pinchGap: number;
}

export function latestLeapTracking(
  events: readonly StoredFabricEvent[],
  allowedNodeIds?: ReadonlySet<string>,
): LeapTrackingReading | undefined {
  const candidates = events
    .filter(
      ({ event }) =>
        event.topic === LEAP_GESTURE_CAPABILITY &&
        (allowedNodeIds === undefined ||
          allowedNodeIds.has(event.sourceNodeId)),
    )
    .sort((left, right) => right.streamSequence - left.streamSequence);
  for (const candidate of candidates) {
    const parsed = parseLeapTracking(candidate);
    if (parsed !== undefined) return parsed;
  }
  return undefined;
}

export function leapHandGeometry(hand: LeapHandSample): LeapHandGeometry {
  return {
    xPercent: clamp(((hand.palmMillimeters.x + 250) / 500) * 100, 6, 94),
    yPercent: clamp(((hand.palmMillimeters.z + 350) / 600) * 100, 6, 94),
    rotationDegrees: clamp(hand.yawDegrees, -90, 90),
    fingerExtension: clamp(1 - hand.grabStrength * 0.72, 0.28, 1),
    pinchGap: clamp(hand.pinchDistanceMillimeters / 70, 0.12, 1),
  };
}

function parseLeapTracking(
  stored: StoredFabricEvent,
): LeapTrackingReading | undefined {
  const payload = record(stored.event.payload);
  if (payload === undefined) return undefined;
  const tracking = booleanValue(payload.tracking);
  const state = stringValue(payload.state);
  const reason = stringValue(payload.reason);
  const forward = finiteNumber(payload.forwardMetersPerSecond);
  const right = finiteNumber(payload.rightMetersPerSecond);
  const clockwise = finiteNumber(payload.clockwiseRadiansPerSecond);
  const confidence = finiteNumber(stored.event.confidence) ?? 0;
  const totalHandCount = integer(payload.totalHandCount) ?? (tracking ? 1 : 0);
  if (
    tracking === undefined ||
    state === undefined ||
    reason === undefined ||
    forward === undefined ||
    right === undefined ||
    clockwise === undefined
  ) {
    return undefined;
  }
  const hand = parseHand(payload.hand);
  const sensorFrameRateHertz = finiteNumber(payload.sensorFrameRateHertz);
  if (tracking && hand === undefined) return undefined;
  return {
    sourceNodeId: stored.event.sourceNodeId,
    observedAt: String(stored.event.timestamp),
    streamSequence: stored.streamSequence,
    tracking,
    state,
    reason,
    confidence: clamp(confidence, 0, 1),
    totalHandCount: Math.max(0, totalHandCount),
    serviceConnected: booleanValue(payload.serviceConnected) ?? false,
    devicePresent: booleanValue(payload.devicePresent) ?? false,
    ...(hand === undefined ? {} : { hand }),
    ...(sensorFrameRateHertz === undefined ? {} : { sensorFrameRateHertz }),
    command: {
      forwardMetersPerSecond: forward,
      rightMetersPerSecond: right,
      clockwiseRadiansPerSecond: clockwise,
    },
  };
}

function parseHand(value: unknown): LeapHandSample | undefined {
  const hand = record(value);
  if (hand === undefined) return undefined;
  const handedness = stringValue(hand.handedness);
  const handId = integer(hand.handId);
  const visibleTimeSeconds = finiteNumber(hand.visibleTimeSeconds);
  const palmMillimeters = vector(hand.palmMillimeters);
  const velocityMillimetersPerSecond = vector(
    hand.velocityMillimetersPerSecond,
  );
  const direction = vector(hand.direction);
  const palmNormal = vector(hand.palmNormal);
  const pinchStrength = finiteNumber(hand.pinchStrength);
  const grabStrength = finiteNumber(hand.grabStrength);
  const pinchDistanceMillimeters = finiteNumber(hand.pinchDistanceMillimeters);
  const yawDegrees = finiteNumber(hand.yawDegrees);
  if (
    (handedness !== "left" && handedness !== "right") ||
    handId === undefined ||
    visibleTimeSeconds === undefined ||
    palmMillimeters === undefined ||
    velocityMillimetersPerSecond === undefined ||
    direction === undefined ||
    palmNormal === undefined ||
    pinchStrength === undefined ||
    grabStrength === undefined ||
    pinchDistanceMillimeters === undefined ||
    yawDegrees === undefined
  ) {
    return undefined;
  }
  return {
    handId,
    handedness,
    visibleTimeSeconds,
    palmMillimeters,
    velocityMillimetersPerSecond,
    direction,
    palmNormal,
    pinchStrength: clamp(pinchStrength, 0, 1),
    grabStrength: clamp(grabStrength, 0, 1),
    pinchDistanceMillimeters: Math.max(0, pinchDistanceMillimeters),
    yawDegrees,
  };
}

function vector(value: unknown): LeapVector3 | undefined {
  const candidate = record(value);
  if (candidate === undefined) return undefined;
  const x = finiteNumber(candidate.x);
  const y = finiteNumber(candidate.y);
  const z = finiteNumber(candidate.z);
  return x === undefined || y === undefined || z === undefined
    ? undefined
    : { x, y, z };
}

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function finiteNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
}

function integer(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value)
    ? value
    : undefined;
}

function booleanValue(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0
    ? value.trim()
    : undefined;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}
