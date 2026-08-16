import js from "@eslint/js";
import eslintConfigPrettier from "eslint-config-prettier";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/.venv/**",
      "**/artifacts/**",
      "**/dist/**",
      "**/node_modules/**",
      "packages/protocol-ts/src/generated/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.js", "**/*.mjs"],
    languageOptions: { globals: globals.node },
  },
  {
    files: ["apps/studio-web/**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
  },
  eslintConfigPrettier,
);
