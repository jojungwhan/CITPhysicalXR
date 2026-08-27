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

interface VersionedCoursePack {
  coursePackId: string;
  version: string;
}

const compareCourseVersions = (left: string, right: string): number =>
  left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: "base",
  });

/**
 * Keep historical packs available for existing sessions while presenting only
 * the newest installed version when a tutor creates a new lesson.
 */
export const latestCoursePacks = <T extends VersionedCoursePack>(
  coursePacks: readonly T[],
): T[] => {
  const latestById = new Map<string, T>();
  for (const coursePack of coursePacks) {
    const current = latestById.get(coursePack.coursePackId);
    if (
      current === undefined ||
      compareCourseVersions(current.version, coursePack.version) < 0
    ) {
      latestById.set(coursePack.coursePackId, coursePack);
    }
  }
  return [...latestById.values()];
};

const AUTO_FILL_ROLE =
  /^(?:safety_drone|fleet_sequence_input|ground_output|power_output|robot_sensor|glasses_input|message_output)_[1-8]$/;

/**
 * Choose deterministic defaults without guessing between multiple devices for
 * a singular role. Numbered device banks intentionally consume each compatible
 * node once so a tutor can prepare every connected output together.
 */
export const automaticRoleAssignments = (
  roleBindings: readonly RoleBinding[],
  requirements: readonly RoleSelectionRequirement[],
): Record<string, string> => {
  const assignments: Record<string, string> = Object.fromEntries(
    roleBindings.map((binding) => [binding.role, binding.nodeId]),
  );
  const usedNodeIdsByFamily = new Map<string, Set<string>>();
  for (const binding of roleBindings) {
    const family = roleFamily(binding.role);
    const used = usedNodeIdsByFamily.get(family) ?? new Set<string>();
    used.add(binding.nodeId);
    usedNodeIdsByFamily.set(family, used);
  }

  for (const requirement of requirements) {
    if (assignments[requirement.role] !== undefined) continue;
    const family = roleFamily(requirement.role);
    const usedNodeIds = usedNodeIdsByFamily.get(family) ?? new Set<string>();
    const candidates = requirement.candidateNodeIds.filter(
      (nodeId) => !usedNodeIds.has(nodeId),
    );
    if (
      candidates.length === 0 ||
      (candidates.length > 1 && !AUTO_FILL_ROLE.test(requirement.role))
    ) {
      continue;
    }
    const nodeId = candidates[0];
    if (nodeId === undefined) continue;
    assignments[requirement.role] = nodeId;
    usedNodeIds.add(nodeId);
    usedNodeIdsByFamily.set(family, usedNodeIds);
  }
  return assignments;
};

const roleFamily = (role: string): string => role.replace(/_[1-8]$/, "");

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
    delete selections[requirement.role];
  }
  const selectedBindings = Object.entries(selections).map(([role, nodeId]) => ({
    role,
    nodeId,
  }));
  const defaults = automaticRoleAssignments(
    [...roleBindings, ...selectedBindings],
    requirements,
  );
  for (const [role, nodeId] of Object.entries(defaults)) {
    selections[role] ??= nodeId;
  }
  return selections;
};
