import { describe, expect, it } from "vitest";

import {
  exportFilename,
  saveBlobAsFile,
  saveTextAsFile,
  timestampSlug,
  type DownloadPort,
} from "./download.js";

function fakePort(): DownloadPort & {
  saved: { url: string; filename: string }[];
  created: string[];
  revoked: string[];
} {
  const created: string[] = [];
  const revoked: string[] = [];
  const saved: { url: string; filename: string }[] = [];
  return {
    created,
    revoked,
    saved,
    createObjectURL: (blob) => {
      const url = `blob:${blob.type}#${created.length}`;
      created.push(url);
      return url;
    },
    revokeObjectURL: (url) => {
      revoked.push(url);
    },
    save: (url, filename) => {
      saved.push({ url, filename });
    },
    schedule: (work) => work(),
  };
}

const AT = new Date(2026, 7, 17, 10, 32);

describe("export file names", () => {
  it("sorts chronologically as text", () => {
    expect(timestampSlug(AT)).toBe("20260817-1032");
    expect(timestampSlug(new Date(2026, 0, 2, 3, 4))).toBe("20260102-0304");
  });

  it("names the document, what it is of, and when", () => {
    expect(exportFilename("replay", "rec-42", AT, "json")).toBe(
      "citxr-replay-rec-42-20260817-1032.json",
    );
  });

  it("reduces a label to something every filesystem accepts", () => {
    expect(exportFilename("project", "내 프로그램 / v2", AT, "json")).toMatch(
      /^citxr-project-[^/\\:*?"<>|]+-20260817-1032\.json$/,
    );
    expect(
      exportFilename("project", "내 프로그램 / v2", AT, "json"),
    ).not.toContain("/");
  });

  it("leaves no stray separator when the label reduces to nothing", () => {
    expect(exportFilename("audit", "///", AT, "jsonl")).toBe(
      "citxr-audit-20260817-1032.jsonl",
    );
    expect(exportFilename("audit", null, AT, "jsonl")).toBe(
      "citxr-audit-20260817-1032.jsonl",
    );
  });
});

describe("saving a document as a file", () => {
  it("hands the browser a blob under the name it was given", () => {
    const port = fakePort();
    const name = saveTextAsFile(
      "a\nb\n",
      "log.jsonl",
      "application/x-ndjson",
      port,
    );

    expect(name).toBe("log.jsonl");
    expect(port.saved).toEqual([
      { url: port.created[0], filename: "log.jsonl" },
    ]);
    expect(port.created[0]).toContain("application/x-ndjson");
  });

  it("revokes the url it created, so exports do not accumulate in memory", () => {
    const port = fakePort();
    saveTextAsFile("{}", "a.json", "application/json", port);
    saveTextAsFile("{}", "b.json", "application/json", port);

    expect(port.revoked).toEqual(port.created);
  });

  it("revokes the url even when the browser refuses to save", () => {
    const port = fakePort();
    port.save = () => {
      throw new Error("save blocked");
    };

    expect(() =>
      saveTextAsFile("{}", "a.json", "application/json", port),
    ).toThrow("save blocked");
    expect(port.revoked).toHaveLength(1);
  });

  it("saves an authenticated binary response without reconstructing its bytes", () => {
    const port = fakePort();
    const blob = new Blob([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], {
      type: "application/zip",
    });

    expect(saveBlobAsFile(blob, "CIT-Setup.zip", port)).toBe("CIT-Setup.zip");
    expect(port.saved).toEqual([
      { url: port.created[0], filename: "CIT-Setup.zip" },
    ]);
    expect(port.created[0]).toContain("application/zip");
    expect(port.revoked).toEqual(port.created);
  });
});
