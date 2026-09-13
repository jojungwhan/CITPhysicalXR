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

  it("stages a model locally with a canonical type and encoded Unicode filename", async () => {
    const artifact = {
      artifactId: "a".repeat(32),
      fileName: "교실 모형.3mf",
      mediaType: "model/3mf",
      sizeBytes: 4,
      sha256: "b".repeat(64),
      createdAt: "2026-09-08T12:00:00Z",
    };
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify(artifact), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    const token = "cit-instructor-" + "p".repeat(40);
    client.setCredential(token);
    const file = new File(
      [new Uint8Array([0x50, 0x4b, 0x03, 0x04])],
      "교실 모형.3mf",
      {
        type: "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
      },
    );

    await expect(client.stagePrinterSource(file)).resolves.toEqual(artifact);

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    const headers = new Headers(init?.headers);
    expect(url).toBe(
      "https://runtime.example.test/api/v1/fabric/printer/sources",
    );
    expect(headers.get("Authorization")).toBe(`Bearer ${token}`);
    expect(headers.get("Content-Type")).toBe("model/3mf");
    expect(headers.get("X-CIT-Filename")).toBe(
      encodeURIComponent("교실 모형.3mf"),
    );
    expect(init?.body).toBe(file);
  });

  it("starts only one exact printer artifact with explicit physical confirmations", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ accepted: true, message: "started", snapshot: {} }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    client.setCredential("cit-instructor-" + "q".repeat(40));
    const artifactId = "c".repeat(32);
    const confirmationToken = "one-time-printer-token-" + "d".repeat(32);

    await client.startPrinterArtifact(artifactId, confirmationToken, {
      plateClearConfirmed: true,
      profileConfirmed: true,
    });

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe(
      `https://runtime.example.test/api/v1/fabric/printer/artifacts/${artifactId}/start`,
    );
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      confirmationToken,
      plateClearConfirmed: true,
      profileConfirmed: true,
    });
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

  it("renames one exact Matter plug with a bounded request body", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          schemaVersion: "1.0",
          entries: [
            {
              setupCode: "12345678901",
              matterNodeIds: ["19"],
              name: "Window lamp",
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const client = new FabricClient("http://127.0.0.1:8766", fetchMock);
    client.setCredential("cit-instructor-" + "n".repeat(40));

    await client.renameMatterPlug("19", "Window lamp");

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://127.0.0.1:8766/api/v1/fabric/matter/plug-name");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({
      matterNodeId: "19",
      name: "Window lamp",
    });
    expect(() => client.renameMatterPlug("../19", "Window lamp")).toThrow(
      "identifier is invalid",
    );
    expect(() => client.renameMatterPlug("19", " Window lamp")).toThrow(
      "between 1 and 64",
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
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

  it("addresses one configured camera import by its encoded identifier", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            accepted: true,
            message: "started",
            snapshot: {},
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    client.setCredential("cit-instructor-" + "n".repeat(40));

    await client.startNamedCameraImport("dji-osmo-nano-android");
    await client.openNamedCameraImportDestination("dji-osmo-nano-android");

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "https://runtime.example.test/api/v1/fabric/camera-imports/dji-osmo-nano-android/start",
    );
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      "https://runtime.example.test/api/v1/fabric/camera-imports/dji-osmo-nano-android/open-destination",
    );
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
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
    expect(redeemInit?.credentials).toBe("omit");
    expect(JSON.parse(String(redeemInit?.body))).toEqual({ ticket });
    const [, identityInit] = fetchMock.mock.calls[1] ?? [];
    expect(new Headers(identityInit?.headers).get("Authorization")).toBe(
      `Bearer ${accessToken}`,
    );
  });

  it("restores Android auth into memory through the path-scoped cookie", async () => {
    const accessToken = "cit-android-" + "r".repeat(40);
    const principal = {
      identityId: "android-controller-a",
      actorType: "android_controller",
      roles: ["instructor"],
      permissions: ["fabric.nodes.read"],
      expiresAt: "2026-09-09T15:00:00Z",
    };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            accessToken,
            expiresAt: principal.expiresAt,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(principal), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    const client = new FabricClient("https://runtime.example.test", fetchMock);

    await expect(client.resumeAndroidSession()).resolves.toEqual(principal);

    const [resumeUrl, resumeInit] = fetchMock.mock.calls[0] ?? [];
    expect(resumeUrl).toBe(
      "https://runtime.example.test/api/v1/fabric/auth/android-session/resume",
    );
    expect(resumeInit?.method).toBe("POST");
    expect(resumeInit?.credentials).toBe("include");
    expect(new Headers(resumeInit?.headers).has("Authorization")).toBe(false);
    const [, identityInit] = fetchMock.mock.calls[1] ?? [];
    expect(new Headers(identityInit?.headers).get("Authorization")).toBe(
      `Bearer ${accessToken}`,
    );
    expect(identityInit?.credentials).toBe("omit");
  });

  it("accepts an Android ticket cookie only when the launcher marked the handoff", async () => {
    const accessToken = "cit-android-" + "a".repeat(40);
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            accessToken,
            expiresAt: "2026-09-09T15:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            identityId: "android-controller-a",
            actorType: "android_controller",
            roles: ["instructor"],
            permissions: ["fabric.nodes.read"],
            expiresAt: "2026-09-09T15:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    const client = new FabricClient("https://runtime.example.test", fetchMock);

    await client.connectWithConsoleTicket("m".repeat(43), {
      persistAndroidSession: true,
    });

    expect(fetchMock.mock.calls[0]?.[1]?.credentials).toBe("include");
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      ticket: "m".repeat(43),
    });
  });

  it("reads and opens the USB Android controller through fixed routes", async () => {
    const snapshot = {
      schemaVersion: "1.0",
      state: "ready",
      phoneConnected: true,
      phoneModel: "SM-N971N",
      usbReverseReady: true,
      operations: { openController: true },
      message: "ready",
    };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(snapshot), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ accepted: true, message: "opened", snapshot }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    client.setCredential("cit-instructor-" + "u".repeat(40));

    await expect(client.getAndroidController()).resolves.toEqual(snapshot);
    await expect(client.openAndroidController()).resolves.toMatchObject({
      accepted: true,
    });

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "https://runtime.example.test/api/v1/fabric/android-controller",
    );
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      "https://runtime.example.test/api/v1/fabric/android-controller/open",
    );
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
  });

  it("manages LAN devices only through fixed allowlist routes", async () => {
    const snapshot = {
      schemaVersion: "1.0",
      enabled: true,
      lanOrigin: "http://172.30.1.4:8766",
      devices: [],
      operations: { manage: true, enrollUsbAndroid: true },
    };
    const result = { accepted: true, message: "updated", snapshot };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(snapshot))
      .mockResolvedValueOnce(Response.json(result))
      .mockResolvedValueOnce(Response.json(result))
      .mockResolvedValueOnce(Response.json(result))
      .mockResolvedValueOnce(
        Response.json({
          schemaVersion: "1.0",
          accessUrl:
            "http://192.168.50.10:8766/fabric#android-console-ticket=one-use",
          expiresAt: "2026-09-10T03:01:30Z",
        }),
      );
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    client.setCredential("cit-instructor-" + "w".repeat(40));

    await client.getLanAccess();
    await client.addLanAccessDevice("Spare phone", "02:11:22:33:44:55");
    await client.removeLanAccessDevice("02:11:22:33:44:55");
    await client.enrollUsbAndroidLanAccess();
    await client.createLanAccessLink("02:11:22:33:44:55");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "https://runtime.example.test/api/v1/fabric/lan-access",
      "https://runtime.example.test/api/v1/fabric/lan-access/devices",
      "https://runtime.example.test/api/v1/fabric/lan-access/devices/02%3A11%3A22%3A33%3A44%3A55",
      "https://runtime.example.test/api/v1/fabric/lan-access/enroll-usb-android",
      "https://runtime.example.test/api/v1/fabric/lan-access/devices/02%3A11%3A22%3A33%3A44%3A55/access-link",
    ]);
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      displayName: "Spare phone",
      macAddress: "02:11:22:33:44:55",
    });
    expect(fetchMock.mock.calls[2]?.[1]?.method).toBe("DELETE");
    expect(fetchMock.mock.calls[4]?.[1]?.method).toBe("POST");
  });

  it("manages unlock automation only through fixed local administration routes", async () => {
    const snapshot = {
      schemaVersion: "1.0",
      enabled: false,
      selectedNodeIds: ["plug-19", "plug-22"],
      cooldownSeconds: 15,
      operations: { manage: true, installAndPair: true },
    };
    const result = { accepted: true, message: "updated", snapshot };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(snapshot))
      .mockResolvedValueOnce(Response.json(result))
      .mockResolvedValueOnce(Response.json(result))
      .mockResolvedValueOnce(Response.json(result));
    const client = new FabricClient("https://runtime.example.test", fetchMock);
    client.setCredential("cit-instructor-" + "x".repeat(40));

    await client.getUnlockAutomation();
    await client.configureUnlockAutomation(true, ["plug-19", "plug-22"]);
    await client.installAndPairUnlockCompanion("SM-N971N");
    await client.removeUnlockCompanion();

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "https://runtime.example.test/api/v1/fabric/unlock-automation",
      "https://runtime.example.test/api/v1/fabric/unlock-automation/configuration",
      "https://runtime.example.test/api/v1/fabric/unlock-automation/companion/pair-usb",
      "https://runtime.example.test/api/v1/fabric/unlock-automation/companion",
    ]);
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("PUT");
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      enabled: true,
      selectedNodeIds: ["plug-19", "plug-22"],
    });
    expect(fetchMock.mock.calls[2]?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({
      displayName: "SM-N971N",
    });
    expect(fetchMock.mock.calls[3]?.[1]?.method).toBe("DELETE");
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain("secret");
  });
});
