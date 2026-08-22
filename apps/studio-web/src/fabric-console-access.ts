const TICKET_KEY = "console-ticket";

interface ConsoleLocation {
  hash: string;
  pathname: string;
  search: string;
}

interface ConsoleHistory {
  replaceState(data: unknown, unused: string, url?: string | URL | null): void;
}

export const consumeConsoleTicket = (
  location: ConsoleLocation,
  history: ConsoleHistory,
): string | undefined => {
  const parameters = new URLSearchParams(location.hash.replace(/^#/, ""));
  const ticket = parameters.get(TICKET_KEY) ?? undefined;
  if (ticket === undefined) return undefined;
  history.replaceState(null, "", `${location.pathname}${location.search}`);
  return ticket;
};
