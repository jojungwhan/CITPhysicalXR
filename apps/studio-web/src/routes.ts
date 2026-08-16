import type { MessageKey } from "./i18n.js";

/**
 * UI 11.1. The navigation the PRD names, in the order it names it.
 *
 * This lives apart from `App.tsx` on purpose. `App` imports the Blockly
 * workspace, Blockly's Node entry point requires `jsdom`, and `jsdom` is
 * deliberately not installed here -- Milestone 3 dropped it rather than widen
 * the licence allowlist. Keeping the routing table in a module of its own means
 * it stays testable without dragging an editor into a unit test.
 */
export const ROUTES = [
  "projects",
  "program",
  "devices",
  "xr",
  "simulation",
  "instructor",
  "logs",
  "settings",
] as const;

export type Route = (typeof ROUTES)[number];

export const NAV_LABEL: Record<Route, MessageKey> = {
  projects: "nav.projects",
  program: "nav.program",
  devices: "nav.devices",
  xr: "nav.xr",
  simulation: "nav.simulation",
  instructor: "nav.instructor",
  logs: "nav.logs",
  settings: "nav.settings",
};

/** An unknown or empty hash lands on the program, never on a blank page. */
export function routeFromHash(hash: string): Route {
  const name = hash.replace(/^#\/?/, "");
  return (ROUTES as readonly string[]).includes(name)
    ? (name as Route)
    : "program";
}
