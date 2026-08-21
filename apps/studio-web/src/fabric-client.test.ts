import { describe, expect, it, vi } from "vitest";

import { FabricClient } from "./fabric-client.js";

describe("Fabric client credentials", () => {
  it("keeps the credential out of URLs and sends it only as a bearer header", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          identityId: "instructor-a",
          actorType: "instructor",
          roles: ["instructor"],
          permissions: ["fabric.nodes.read"],
          expiresAt: "2026-08-22T03:00:00Z",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    const token = "cit-instructor-" + "a".repeat(40);
    client.setCredential(token);

    await client.whoAmI();

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("https://runtime.example.test/api/v1/fabric/auth/whoami");
    expect(String(url)).not.toContain(token);
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      `Bearer ${token}`,
    );
    expect(init?.cache).toBe("no-store");
    expect(init?.credentials).toBe("omit");
  });

  it("forgets the in-memory credential when signed out", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    const client = new FabricClient("", fetchMock);
    client.setCredential("cit-instructor-" + "b".repeat(40));
    client.clearCredential();

    await expect(client.listNodes()).rejects.toThrow(
      "Enter a CIT Fabric credential",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
