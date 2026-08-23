type SessionIdentity = { sessionId: string };

/** Preserve the tutor's explicit lesson-builder state across background polls. */
export const refreshedSessionSelection = (
  currentSessionId: string,
  sessions: readonly SessionIdentity[],
): string =>
  currentSessionId !== "" &&
  sessions.some((session) => session.sessionId === currentSessionId)
    ? currentSessionId
    : "";
