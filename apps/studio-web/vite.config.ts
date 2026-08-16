import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  // Relative asset URLs, so one bundle works wherever it is mounted: the
  // runtime serves it from "/", and a static host may serve it from a
  // subdirectory. An absolute "/assets/..." would 404 in the second case.
  base: "./",
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
