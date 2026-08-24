import { createHash } from "node:crypto";

import { describe, expect, it } from "vitest";

import type { FabricInstallationInfo } from "./fabric-client.js";
import {
  createSiteTemplate,
  formatInstallationSize,
  selectWindowsInstallationArtifact,
  verifyInstallationArtifact,
} from "./fabric-installation.js";

const payload = new TextEncoder().encode("portable setup");
const checksum = createHash("sha256").update(payload).digest("hex");
const info: FabricInstallationInfo = {
  schemaVersion: "1.0",
  available: true,
  product: "CITPhysicalXR",
  version: "0.0.0",
  revision: "abcdef1234567890",
  generatedAt: "2026-08-24T04:30:00Z",
  platform: "windows-x64",
  requiresInternet: true,
  artifacts: [
    {
      artifactId: "windows-transfer-online",
      fileName: "CITPhysicalXR-Windows-Setup.zip",
      mediaType: "application/zip",
      sizeBytes: payload.byteLength,
      sha256: checksum,
    },
  ],
};

const digest = async (data: ArrayBuffer): Promise<ArrayBuffer> => {
  const value = createHash("sha256").update(new Uint8Array(data)).digest();
  return value.buffer.slice(
    value.byteOffset,
    value.byteOffset + value.byteLength,
  );
};

describe("portable classroom installation", () => {
  it("selects only the expected verified Windows transfer artifact", () => {
    expect(selectWindowsInstallationArtifact(info)?.fileName).toContain(
      "Windows-Setup",
    );
    expect(
      selectWindowsInstallationArtifact({ ...info, available: false }),
    ).toBeUndefined();
    expect(
      selectWindowsInstallationArtifact({
        ...info,
        artifacts: [{ ...info.artifacts[0]!, sha256: "unverified" }],
      }),
    ).toBeUndefined();
  });

  it("creates a non-secret site template with strict identifiers", () => {
    expect(JSON.parse(createSiteTemplate("cit-seoul", "room-a"))).toEqual({
      schemaVersion: "1.0",
      siteId: "cit-seoul",
      roomId: "room-a",
    });
    expect(createSiteTemplate("cit-seoul", "room-a")).not.toMatch(
      /password|token|credential/i,
    );
    expect(() => createSiteTemplate("../../other", "room-a")).toThrow(
      "not portable",
    );
  });

  it("verifies the downloaded bytes and rejects corruption", async () => {
    const blob = new Blob([payload], { type: "application/zip" });
    await expect(
      verifyInstallationArtifact(blob, checksum, digest),
    ).resolves.toBeUndefined();
    await expect(
      verifyInstallationArtifact(new Blob(["changed"]), checksum, digest),
    ).rejects.toThrow("failed its SHA-256 check");
  });

  it("formats a tutor-readable transfer size", () => {
    expect(formatInstallationSize(3 * 1024 * 1024, "en")).toBe("3 MB");
    expect(formatInstallationSize(512 * 1024, "ko")).toBe("512 KB");
  });
});
