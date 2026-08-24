type SessionIdentity = { sessionId: string };

interface RoleBinding {
  role: string;
  nodeId: string;
}

interface RoleSelectionRequirement {
  role: string;
  optional: boolean;
  candidateNodeIds: readonly string[];
}

/** Preserve the tutor's explicit lesson-builder state across background polls. */
export const refreshedSessionSelection = (
  currentSessionId: string,
  sessions: readonly SessionIdentity[],
): string =>
  currentSessionId !== "" &&
  sessions.some((session) => session.sessionId === currentSessionId)
    ? currentSessionId
    : "";

/** Merge authoritative bindings without erasing an in-progress tutor choice on each poll. */
export const reconciledRoleSelections = (
  currentSelections: Readonly<Record<string, string>>,
  sameSession: boolean,
  roleBindings: readonly RoleBinding[],
  requirements: readonly RoleSelectionRequirement[],
): Record<string, string> => {
  const selections: Record<string, string> = sameSession
    ? { ...currentSelections }
    : {};
  const validRoles = new Set(
    requirements.map((requirement) => requirement.role),
  );

  for (const role of Object.keys(selections)) {
    if (!validRoles.has(role)) delete selections[role];
  }
  for (const binding of roleBindings) {
    selections[binding.role] = binding.nodeId;
  }
  for (const requirement of requirements) {
    if (roleBindings.some((binding) => binding.role === requirement.role)) {
      continue;
    }
    const selectedNodeId = selections[requirement.role];
    if (
      selectedNodeId !== undefined &&
      requirement.candidateNodeIds.includes(selectedNodeId)
    ) {
      continue;
    }
    if (!requirement.optional && requirement.candidateNodeIds.length === 1) {
      selections[requirement.role] = requirement.candidateNodeIds[0] ?? "";
    } else {
      delete selections[requirement.role];
    }
  }
  return selections;
};
