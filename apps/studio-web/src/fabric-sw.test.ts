import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

import { describe, expect, it, vi } from "vitest";

const workerSource = readFileSync(
  new URL("../public/fabric-sw.js", import.meta.url),
  "utf8",
);

describe("Fabric service worker", () => {
  it.each(["", "/citxr"])(
    "installs the shell actually served by Fabric at prefix '%s'",
    async (prefix) => {
      const handlers = new Map<string, (event: unknown) => void>();
      const cached: string[] = [];
      const served = new Set([
        `${prefix}/fabric`,
        `${prefix}/fabric.webmanifest`,
        `${prefix}/favicon.svg`,
        `${prefix}/icons/cit-control-192.png`,
        `${prefix}/icons/cit-control-512.png`,
      ]);
      const caches = {
        open: vi.fn().mockResolvedValue({
          addAll: async (paths: string[]) => {
            for (const path of paths) {
              if (!served.has(path)) throw new Error(`HTTP 404: ${path}`);
              cached.push(path);
            }
          },
        }),
        match: vi.fn().mockResolvedValue(new Response("offline shell")),
      };
      runInNewContext(workerSource, {
        URL,
        caches,
        fetch: vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
        self: {
          registration: { scope: `https://cit.test${prefix}/` },
          location: { origin: "https://cit.test" },
          addEventListener: (
            name: string,
            callback: (event: unknown) => void,
          ) => handlers.set(name, callback),
          skipWaiting: vi.fn(),
        },
      });
      let installation: Promise<unknown> | undefined;
      handlers.get("install")!({
        waitUntil: (pending: Promise<unknown>) => {
          installation = pending;
        },
      });
      await installation;
      expect(cached).toContain(`${prefix}/fabric`);

      let fallback: Promise<Response> | undefined;
      handlers.get("fetch")!({
        request: {
          url: `https://cit.test${prefix}/fabric`,
          method: "GET",
          mode: "navigate",
        },
        respondWith: (pending: Promise<Response>) => {
          fallback = pending;
        },
      });
      expect(await (await fallback)?.text()).toBe("offline shell");
      expect(caches.match).toHaveBeenCalledWith(`${prefix}/fabric`);

      const respondWith = vi.fn();
      handlers.get("fetch")!({
        request: {
          url: `https://cit.test${prefix}/api/v1/fabric/nodes`,
          method: "GET",
          mode: "cors",
        },
        respondWith,
      });
      expect(respondWith).not.toHaveBeenCalled();
    },
  );
});
