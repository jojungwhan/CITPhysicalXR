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

  it("downloads the Windows installer with the bearer header and no credential URL", async () => {
    const bytes = new Uint8Array([0x50, 0x4b, 0x03, 0x04]);
    const checksum = "a".repeat(64);
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(bytes, {
        status: 200,
        headers: {
          "Content-Type": "application/zip",
          "X-CIT-SHA256": checksum,
        },
      }),
    );
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    const token = "cit-instructor-" + "i".repeat(40);
    client.setCredential(token);

    const result = await client.downloadInstallationArtifact(
      "windows-transfer-online",
    );

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe(
      "https://runtime.example.test/api/v1/fabric/installation/artifacts/windows-transfer-online",
    );
    expect(String(url)).not.toContain(token);
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      `Bearer ${token}`,
    );
    expect(new Headers(init?.headers).get("Accept")).toBe("application/zip");
    expect(result.sha256).toBe(checksum);
    expect(Array.from(new Uint8Array(await result.blob.arrayBuffer()))).toEqual(
      Array.from(bytes),
    );
    await expect(
      client.downloadInstallationArtifact("../../escape"),
    ).rejects.toThrow("identifier is invalid");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("uses fixed same-origin discovery routes and a structured grounded confirmation", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          actionId: "brain2devices.tello.connect-all",
          accepted: true,
          message: "Connection started.",
          report: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    client.setCredential("cit-instructor-" + "d".repeat(40));

    await client.runDiscoveryAction("brain2devices.tello.connect-all", true);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe(
      "https://runtime.example.test/api/v1/fabric/discovery/actions/brain2devices.tello.connect-all",
    );
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      confirmGrounded: true,
    });
    expect(() => client.runDiscoveryAction("../../shell", true)).toThrow(
      "connection action is invalid",
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("can scope lifecycle polling to one exact command", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response("[]", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    client.setCredential("cit-instructor-" + "l".repeat(40));

    await client.listLifecycle(0, "command-a");

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "https://runtime.example.test/api/v1/fabric/commands/lifecycle?afterSequence=0&limit=100&commandId=command-a",
    );
  });

  it("attaches a fixed glasses action to one exact lesson session", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          actionId: "cit.glasses-device-control.connect",
          accepted: true,
          message: "Attached.",
          report: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    client.setCredential("cit-instructor-" + "d".repeat(40));

    await client.runDiscoveryAction(
      "cit.glasses-device-control.connect",
      false,
      "glasses-session-01",
    );

    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(JSON.parse(String(init?.body))).toEqual({
      confirmGrounded: false,
      sessionId: "glasses-session-01",
    });
    expect(() =>
      client.runDiscoveryAction(
        "cit.glasses-device-control.connect",
        false,
        "../../wrong",
      ),
    ).toThrow("session identifier is invalid");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("uses dedicated remembered-device routes without invoking a scan", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            schemaVersion: "1.0",
            hostId: "classroom-host",
            connections: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            schemaVersion: "1.0",
            connectedCount: 0,
            alreadyConnectedCount: 0,
            skippedCount: 0,
            failedCount: 0,
            outcomes: [],
            report: {},
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    client.setCredential("cit-instructor-" + "r".repeat(40));

    await client.listRememberedConnections();
    await client.reconnectRememberedDevices(true);

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "https://runtime.example.test/api/v1/fabric/discovery/remembered",
    );
    const [url, init] = fetchMock.mock.calls[1] ?? [];
    expect(url).toBe(
      "https://runtime.example.test/api/v1/fabric/discovery/remembered/connect",
    );
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ confirmGrounded: true });
    expect(
      fetchMock.mock.calls.some(([value]) => String(value).endsWith("/scan")),
    ).toBe(false);
  });

  it("sends a Matter setup code only in the authenticated request body", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          actionId: "cit.matter-smart-plug.commission",
          accepted: true,
          message: "Commissioned.",
          report: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new FabricClient("http://127.0.0.1:8766", fetchMock);
    client.setCredential("cit-instructor-" + "m".repeat(40));

    await client.commissionMatterPlug("MT:Y.K9042C00KA0648G00");

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://127.0.0.1:8766/api/v1/fabric/matter/commission");
    expect(String(url)).not.toContain("MT:");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      setupCode: "MT:Y.K9042C00KA0648G00",
    });
  });

  it("sends Matter Wi-Fi credentials only in the authenticated request body", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          actionId: "cit.matter-smart-plug.configure-wifi",
          accepted: true,
          message: "Configured.",
          report: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new FabricClient("http://127.0.0.1:8766", fetchMock);
    client.setCredential("cit-instructor-" + "w".repeat(40));
    const password = "private-classroom-passphrase";

    await client.configureMatterWifi("CIT-Classroom-2G", password);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://127.0.0.1:8766/api/v1/fabric/matter/wifi");
    expect(String(url)).not.toContain(password);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      ssid: "CIT-Classroom-2G",
      password,
    });
  });

  it("sends a bounded LEGO profile to the fixed same-origin route", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          actionId: "cit.lego-pybricks.configure-connect",
          accepted: true,
          message: "Connected.",
          report: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new FabricClient("http://127.0.0.1:8766", fetchMock);
    client.setCredential("cit-instructor-" + "l".repeat(40));
    const configuration = {
      hubName: "CIT LEGO A",
      hubModel: "spike-prime" as const,
      ports: {
        A: "motor" as const,
        B: "motor" as const,
        C: "distance" as const,
      },
    };

    await client.connectLegoHub(configuration);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://127.0.0.1:8766/api/v1/fabric/lego/connect");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual(configuration);
  });

  it("sends only exact opaque Dash/Dot selections to the fixed route", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          actionId: "cit.wonder-workshop.configure-connect",
          accepted: true,
          message: "Connected.",
          report: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new FabricClient("http://127.0.0.1:8766", fetchMock);
    client.setCredential("cit-instructor-" + "w".repeat(40));
    const robots = [
      { candidateId: "wonder-aabbccddeeff", model: "dash" as const },
      { candidateId: "wonder-001122334455", model: "dot" as const },
    ];

    await client.connectWonderWorkshop(robots);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe(
      "http://127.0.0.1:8766/api/v1/fabric/wonder-workshop/connect",
    );
    expect(JSON.parse(String(init?.body))).toEqual({ robots });
    expect(() =>
      client.connectWonderWorkshop([
        { candidateId: "nearest-robot", model: "dash" },
      ]),
    ).toThrow("exact Dash/Dot");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sends only exact opaque Sphero selections to the fixed route", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          actionId: "cit.sphero-bolt.configure-connect",
          accepted: true,
          message: "Connected.",
          report: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new FabricClient("http://127.0.0.1:8766", fetchMock);
    client.setCredential("cit-instructor-" + "s".repeat(40));
    const robots = [
      { candidateId: "sphero-aabbccddeeff" },
      { candidateId: "sphero-001122334455" },
    ];

    await client.connectSpheroBolts(robots);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://127.0.0.1:8766/api/v1/fabric/sphero-bolt/connect");
    expect(JSON.parse(String(init?.body))).toEqual({ robots });
    expect(() =>
      client.connectSpheroBolts([{ candidateId: "nearest-robot" }]),
    ).toThrow("exact Sphero BOLT");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sends exact Ollie selections only to the independent Ollie route", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          actionId: "cit.sphero-ollie.configure-connect",
          accepted: true,
          message: "Connected.",
          report: {},
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new FabricClient("http://127.0.0.1:8766", fetchMock);
    client.setCredential("cit-instructor-" + "o".repeat(40));
    const robots = [{ candidateId: "sphero-ollie-aabbccddeeff" }];

    await client.connectSpheroOllies(robots);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe(
      "http://127.0.0.1:8766/api/v1/fabric/sphero-ollie/connect",
    );
    expect(JSON.parse(String(init?.body))).toEqual({ robots });
    expect(() =>
      client.connectSpheroOllies([{ candidateId: "sphero-aabbccddeeff" }]),
    ).toThrow("exact Sphero Ollie");
    expect(fetchMock).toHaveBeenCalledTimes(1);
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

  it("reads server-derived session start safety policy", async () => {
    const policy = {
      sessionId: "session-a",
      requiresArming: false,
    };
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(policy), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const client = new FabricClient("http://127.0.0.1:8766", fetchMock);
    client.setCredential("cit-instructor-" + "p".repeat(40));

    await expect(client.getSessionStartPolicy("session-a")).resolves.toEqual(
      policy,
    );

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "http://127.0.0.1:8766/api/v1/fabric/sessions/session-a/start-policy",
    );
  });

  it("requests the latest chronological event window for the live console", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const client = new FabricClient("http://127.0.0.1:8766", fetchMock);
    client.setCredential("cit-instructor-" + "e".repeat(40));

    await client.listEvents("session-a");

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "http://127.0.0.1:8766/api/v1/fabric/events?sessionId=session-a&afterSequence=0&limit=100&latest=true",
    );
  });

  it("creates a bounded Meta camera pairing without accepting device credentials", async () => {
    const pairing = {
      pairingId: "media-pairing-a",
      pairingCode: "pairing-code-abcdefghijkl",
      expiresAt: "2026-08-22T03:05:00Z",
      fabricOrigin: "http://192.168.10.20:8766",
      siteId: "cit-site",
      roomId: "room-a",
      singleUse: true as const,
    };
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(pairing), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    const tutorToken = "cit-tutor-" + "m".repeat(40);
    client.setCredential(tutorToken);

    await expect(
      client.createMediaPairing("cit-site", "room-a"),
    ).resolves.toEqual(pairing);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe(
      "https://runtime.example.test/api/v1/fabric/media/pairings",
    );
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      siteId: "cit-site",
      roomId: "room-a",
    });
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      `Bearer ${tutorToken}`,
    );
  });

  it("redeems a launcher ticket once without sending it as a bearer credential", async () => {
    const accessToken = "cit-tutor-" + "c".repeat(40);
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            accessToken,
            expiresAt: "2026-08-22T03:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            identityId: "tutor-console-a",
            actorType: "instructor",
            roles: ["instructor"],
            permissions: ["fabric.nodes.read"],
            expiresAt: "2026-08-22T03:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    const ticket = "t".repeat(43);

    const principal = await client.connectWithConsoleTicket(ticket);

    expect(principal.identityId).toBe("tutor-console-a");
    const [redeemUrl, redeemInit] = fetchMock.mock.calls[0] ?? [];
    expect(redeemUrl).toBe(
      "https://runtime.example.test/api/v1/fabric/auth/console-tickets/redeem",
    );
    expect(new Headers(redeemInit?.headers).has("Authorization")).toBe(false);
    expect(JSON.parse(String(redeemInit?.body))).toEqual({ ticket });
    const [, identityInit] = fetchMock.mock.calls[1] ?? [];
    expect(new Headers(identityInit?.headers).get("Authorization")).toBe(
      `Bearer ${accessToken}`,
    );
  });
});
