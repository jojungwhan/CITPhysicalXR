import type { FabricMediaSource } from "./fabric-client.js";

/** Avoid noisy frame requests until the ephemeral source has published once. */
export const fabricMediaFrameAvailable = (
  source: Pick<
    FabricMediaSource,
    "state" | "lastFrameAt" | "frameSequence" | "contentType"
  >,
): boolean =>
  source.state === "online" &&
  source.lastFrameAt !== null &&
  source.frameSequence > 0 &&
  source.contentType !== null;
