const AUTO_RECONNECT_STORAGE_KEY = "cit.fabric.auto-reconnect-remembered";

export const resolveAutoReconnectRemembered = (
  stored: string | null | undefined,
): boolean => stored === "true";

export const readAutoReconnectRemembered = (): boolean =>
  typeof window !== "undefined" &&
  resolveAutoReconnectRemembered(
    window.localStorage.getItem(AUTO_RECONNECT_STORAGE_KEY),
  );

export const saveAutoReconnectRemembered = (enabled: boolean): void => {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AUTO_RECONNECT_STORAGE_KEY, String(enabled));
};
