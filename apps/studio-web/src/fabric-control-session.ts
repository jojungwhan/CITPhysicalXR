interface ControlNode {
  nodeId: string;
}

interface ControlSession {
  roleBindings: readonly { role: string; nodeId: string }[];
}

interface DirectControlSession {
  mode: "physical" | "simulation";
  state: string;
  armed?: boolean;
}

export type DirectControlSessionAction = "pause" | "arm" | "start";

export interface PlannedControlAssignment<T extends ControlNode> {
  role: string;
  node: T;
}

/**
 * Plan the audited session transitions hidden behind one explicit device
 * command click. The runtime remains authoritative for authorization and
 * safety; this only removes a redundant preparation button from the console.
 */
export function directControlSessionActions(
  session: DirectControlSession,
): DirectControlSessionAction[] {
  if (!["ready", "paused", "active"].includes(session.state)) return [];

  const actions: DirectControlSessionAction[] = [];
  const needsArm = session.mode === "physical" && session.armed !== true;
  if (needsArm && session.state === "active") actions.push("pause");
  if (needsArm) actions.push("arm");
  if (session.state !== "active" || needsArm) actions.push("start");
  return actions;
}

export const sessionCoversNodes = (
  session: ControlSession,
  nodes: readonly ControlNode[],
  acceptsRole: (role: string) => boolean = () => true,
): boolean =>
  nodes.length > 0 &&
  nodes.every((node) =>
    session.roleBindings.some(
      (binding) => binding.nodeId === node.nodeId && acceptsRole(binding.role),
    ),
  );

/**
 * Keep controls visible before their private control session exists. Existing
 * bindings remain authoritative; otherwise the same deterministic role plan
 * is used when the session is created on the first safe action.
 */
export function plannedControlAssignments<T extends ControlNode>(
  nodes: readonly T[],
  session: ControlSession | undefined,
  roleForIndex: (index: number) => string,
  acceptsRole: (role: string) => boolean = () => true,
): PlannedControlAssignment<T>[] {
  return nodes.map((node, index) => ({
    role:
      session?.roleBindings.find(
        (binding) =>
          binding.nodeId === node.nodeId && acceptsRole(binding.role),
      )?.role ?? roleForIndex(index),
    node,
  }));
}
