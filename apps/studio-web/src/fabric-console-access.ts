const TICKET_KEY = "console-ticket";
const ANDROID_TICKET_KEY = "android-console-ticket";

interface ConsoleLocation {
  hash: string;
  pathname: string;
  search: string;
}

interface ConsoleHistory {
  replaceState(data: unknown, unused: string, url?: string | URL | null): void;
}

export interface ConsoleAccessHandoff {
  ticket: string;
  persistAndroidSession: boolean;
}

export const consumeConsoleAccess = (
  location: ConsoleLocation,
  history: ConsoleHistory,
): ConsoleAccessHandoff | undefined => {
  const parameters = new URLSearchParams(location.hash.replace(/^#/, ""));
  const androidTicket = parameters.get(ANDROID_TICKET_KEY) ?? undefined;
  const ticket = androidTicket ?? parameters.get(TICKET_KEY) ?? undefined;
  if (ticket === undefined) return undefined;
  history.replaceState(null, "", `${location.pathname}${location.search}`);
  return {
    ticket,
    persistAndroidSession: androidTicket !== undefined,
  };
};

export const consumeConsoleTicket = (
  location: ConsoleLocation,
  history: ConsoleHistory,
): string | undefined => consumeConsoleAccess(location, history)?.ticket;
