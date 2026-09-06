import type { FlowTarget } from "./generated/models.js";

/** Return the complete statically bounded role set for any flow target form. */
export const flowTargetRoles = (target: FlowTarget): readonly string[] =>
  "role" in target
    ? [target.role]
    : "roles" in target
      ? target.roles
      : target.allowedRoles;
