import type { FabricDiscoveryCandidate } from "./fabric-client.js";
import { fabricTranslatorFor, type FabricTranslate } from "./fabric-i18n.js";

const LINK_STATE_KEYS: Record<
  NonNullable<FabricDiscoveryCandidate["linkState"]>,
  | "link.attached"
  | "link.connected"
  | "link.recent"
  | "link.visible"
  | "link.paired"
  | "link.provisioned"
  | "link.ready"
> = {
  attached: "link.attached",
  connected: "link.connected",
  recently_active: "link.recent",
  visible: "link.visible",
  paired: "link.paired",
  provisioned: "link.provisioned",
  ready: "link.ready",
};

export const discoveryLinkLabel = (
  candidate: FabricDiscoveryCandidate,
  t: FabricTranslate = fabricTranslatorFor("en"),
): string | undefined =>
  candidate.linkState === undefined
    ? undefined
    : t(LINK_STATE_KEYS[candidate.linkState]);
