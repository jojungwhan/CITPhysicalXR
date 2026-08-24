import type {
  FabricInstallationArtifact,
  FabricInstallationInfo,
} from "./fabric-client.js";

const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const SHA256 = /^[a-f0-9]{64}$/;

export function selectWindowsInstallationArtifact(
  info: FabricInstallationInfo | null,
): FabricInstallationArtifact | undefined {
  if (info?.available !== true || info.platform !== "windows-x64") {
    return undefined;
  }
  return info.artifacts.find(
    (artifact) =>
      artifact.artifactId === "windows-transfer-online" &&
      artifact.mediaType === "application/zip" &&
      artifact.sizeBytes > 0 &&
      SHA256.test(artifact.sha256),
  );
}

export function formatInstallationSize(bytes: number, locale: string): string {
  const divisor = bytes >= 1024 * 1024 ? 1024 * 1024 : 1024;
  const unit = divisor === 1024 * 1024 ? "MB" : "KB";
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(bytes / divisor)} ${unit}`;
}

export function createSiteTemplate(siteId: string, roomId: string): string {
  if (!IDENTIFIER.test(siteId) || !IDENTIFIER.test(roomId)) {
    throw new Error("Site and room identifiers are not portable.");
  }
  return `${JSON.stringify(
    {
      schemaVersion: "1.0",
      siteId,
      roomId,
    },
    null,
    2,
  )}\n`;
}

export async function sha256Hex(
  blob: Blob,
  digest: (data: ArrayBuffer) => Promise<ArrayBuffer> = (data) =>
    crypto.subtle.digest("SHA-256", data),
): Promise<string> {
  const value = await digest(await blob.arrayBuffer());
  return Array.from(new Uint8Array(value), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

export async function verifyInstallationArtifact(
  blob: Blob,
  expectedSha256: string,
  digest?: (data: ArrayBuffer) => Promise<ArrayBuffer>,
): Promise<void> {
  if (!SHA256.test(expectedSha256)) {
    throw new Error("The installation checksum is invalid.");
  }
  const actual = await sha256Hex(blob, digest);
  if (actual !== expectedSha256) {
    throw new Error(
      "The downloaded installation package failed its SHA-256 check.",
    );
  }
}
