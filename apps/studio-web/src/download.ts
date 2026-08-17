/**
 * Handing a document to the browser as a file (FR-084).
 *
 * The audit log, a replay package, and a project are all fetched with the
 * runtime token in an `Authorization` header, so none of them can be a plain
 * link the browser follows: a link carries no header, and putting the token in
 * a query string would write it into history. The document is therefore already
 * in memory by the time anybody wants it saved, and what is left is turning
 * bytes into a file the person can keep.
 *
 * Everything that touches the DOM is injected. The Studio's tests run in Node
 * without a DOM -- `jsdom` was dropped at Milestone 3 rather than widen the
 * licence allowlist -- so a module that reached for `document` directly would
 * be a module with no tests.
 */

export interface DownloadPort {
  createObjectURL(blob: Blob): string;
  revokeObjectURL(url: string): void;
  /** Ask the browser to save `url` under `filename`. */
  save(url: string, filename: string): void;
  /** Run cleanup after the browser has had the URL. */
  schedule(work: () => void): void;
}

/** The date part of an export's name: `20260817-1032`, sorting chronologically. */
export function timestampSlug(at: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return (
    `${at.getFullYear()}${pad(at.getMonth() + 1)}${pad(at.getDate())}` +
    `-${pad(at.getHours())}${pad(at.getMinutes())}`
  );
}

/**
 * A file name a person can find again.
 *
 * The label is whatever the document is of -- a recording id, a project name --
 * and is reduced to characters that are a file name on every supported system.
 * A label that reduces to nothing is dropped rather than leaving a stray
 * separator.
 */
export function exportFilename(
  kind: string,
  label: string | null,
  at: Date,
  extension: string,
): string {
  const safe = (label ?? "")
    .normalize("NFKD")
    .replace(/[^\p{Letter}\p{Number}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48)
    .toLowerCase();
  const parts = ["citxr", kind, safe, timestampSlug(at)].filter(
    (part) => part !== "",
  );
  return `${parts.join("-")}.${extension}`;
}

/** The browser's own implementation, when there is a browser. */
export function browserDownloadPort(): DownloadPort {
  return {
    createObjectURL: (blob) => URL.createObjectURL(blob),
    revokeObjectURL: (url) => URL.revokeObjectURL(url),
    save: (url, filename) => {
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      // Attached before clicking: a detached anchor is ignored by Firefox.
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
    },
    // Not immediately after the click: a browser reads the object URL while it
    // starts the download, and revoking it in the same turn saves an empty
    // file in some of them.
    schedule: (work) => {
      window.setTimeout(work, 0);
    },
  };
}

/**
 * Save one text document as a file. Returns the name it was saved under.
 *
 * The object URL is always revoked, because a page that exports a lesson's
 * recordings one after another would otherwise hold every one of them in
 * memory until it was closed.
 */
export function saveTextAsFile(
  text: string,
  filename: string,
  contentType: string,
  port: DownloadPort = browserDownloadPort(),
): string {
  const url = port.createObjectURL(
    new Blob([text], { type: `${contentType};charset=utf-8` }),
  );
  try {
    port.save(url, filename);
  } finally {
    port.schedule(() => port.revokeObjectURL(url));
  }
  return filename;
}
