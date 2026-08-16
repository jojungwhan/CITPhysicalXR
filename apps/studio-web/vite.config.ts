import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const require = createRequire(import.meta.url);

/**
 * The runtime files Pyodide fetches at load time.
 *
 * They are copied out of node_modules into the bundle so the Studio never
 * reaches a CDN. FR-085 requires the whole system to work with the network
 * unplugged, and a classroom on a locked-down school network is the normal
 * case, not the edge case.
 */
const PYODIDE_RUNTIME_FILES = [
  "pyodide.asm.js",
  "pyodide.asm.mjs",
  "pyodide.asm.wasm",
  "python_stdlib.zip",
  "pyodide-lock.json",
];

function vendorPyodide(): Plugin {
  return {
    name: "citxr-vendor-pyodide",
    apply: "build",
    generateBundle() {
      const source = path.dirname(require.resolve("pyodide/package.json"));
      const target = path.resolve(import.meta.dirname, "dist", "pyodide");
      mkdirSync(target, { recursive: true });
      for (const file of PYODIDE_RUNTIME_FILES) {
        try {
          copyFileSync(path.join(source, file), path.join(target, file));
        } catch (error) {
          // Pyodide ships either the .js or the .mjs asm build depending on
          // version; a missing optional file is not a broken build.
          if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
        }
      }
    },
  };
}

export default defineConfig({
  // Relative asset URLs, so one bundle works wherever it is mounted: the
  // runtime serves it from "/", and a static host may serve it from a
  // subdirectory. An absolute "/assets/..." would 404 in the second case.
  base: "./",
  plugins: [react(), vendorPyodide()],
  worker: { format: "es" },
  build: {
    outDir: "dist",
    sourcemap: true,
    chunkSizeWarningLimit: 1200,
  },
});
