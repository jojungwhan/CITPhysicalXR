import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: [
      "apps/**/*.test.ts",
      "apps/**/*.test.tsx",
      "packages/**/*.test.ts",
      "tests/**/*.test.ts",
    ],
    exclude: ["**/node_modules/**", "**/dist/**"],
  },
});
