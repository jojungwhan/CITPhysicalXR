interface DemonstrationNodeIdentity {
  nodeId: string;
}

export const DEMONSTRATION_SELECTION_STORAGE_KEY =
  "citxr.fabric.demonstrationSelection.v1";

type DemonstrationSelectionStorage = Pick<
  Storage,
  "getItem" | "setItem" | "removeItem"
>;

const MAX_DEMONSTRATION_DEVICES = 256;

const validDemonstrationNodeId = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0 && value.length <= 256;

const browserLocalStorage = (): DemonstrationSelectionStorage | undefined => {
  if (typeof window === "undefined") return undefined;
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
};

/** Missing storage means the dynamic default: select every connected device. */
export function readDemonstrationSelection(
  storage: DemonstrationSelectionStorage | undefined = browserLocalStorage(),
): ReadonlySet<string> | null {
  if (storage === undefined) return null;
  try {
    const saved = storage.getItem(DEMONSTRATION_SELECTION_STORAGE_KEY);
    if (saved === null) return null;
    const parsed: unknown = JSON.parse(saved);
    if (!Array.isArray(parsed)) return null;
    return new Set(
      parsed
        .filter(validDemonstrationNodeId)
        .slice(0, MAX_DEMONSTRATION_DEVICES),
    );
  } catch {
    return null;
  }
}

/** Null keeps the dynamic select-all default; an empty set is explicit. */
export function saveDemonstrationSelection(
  nodeIds: Iterable<string> | null,
  storage: DemonstrationSelectionStorage | undefined = browserLocalStorage(),
): void {
  if (storage === undefined) return;
  try {
    if (nodeIds === null) {
      storage.removeItem(DEMONSTRATION_SELECTION_STORAGE_KEY);
      return;
    }
    const normalized = Array.from(new Set(nodeIds))
      .filter(validDemonstrationNodeId)
      .slice(0, MAX_DEMONSTRATION_DEVICES);
    storage.setItem(
      DEMONSTRATION_SELECTION_STORAGE_KEY,
      JSON.stringify(normalized),
    );
  } catch {
    // Browser privacy settings or a full quota must not break device controls.
  }
}

export const allDemonstrationNodeIds = <T extends DemonstrationNodeIdentity>(
  nodes: readonly T[],
): ReadonlySet<string> => new Set(nodes.map((node) => node.nodeId));

export const selectedDemonstrationNodes = <T extends DemonstrationNodeIdentity>(
  nodes: readonly T[],
  selectedNodeIds: ReadonlySet<string>,
): T[] => nodes.filter((node) => selectedNodeIds.has(node.nodeId));

export const toggledDemonstrationNodeIds = (
  selectedNodeIds: ReadonlySet<string>,
  nodeId: string,
  selected: boolean,
): ReadonlySet<string> => {
  const next = new Set(selectedNodeIds);
  if (selected) next.add(nodeId);
  else next.delete(nodeId);
  return next;
};
