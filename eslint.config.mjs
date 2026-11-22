// ESLint as in the Home Assistant frontend: @eslint/js recommended plus the extra core rules of
// its eslint.config.mjs, kept in tests/eslint-ha.json. The card is plain JavaScript without a
// build step, so the TypeScript and Lit plugins of the frontend do not apply.
import { readFileSync } from "node:fs";
import js from "@eslint/js";

const ha = JSON.parse(
  readFileSync(new URL("./tests/eslint-ha.json", import.meta.url), "utf8")
);

export default [
  {
    ignores: [
      "lokaal/**",
      "node_modules/**",
      ".claude/**",
      "custom_components/grib_overlay/www/vendor/**",
    ],
  },
  js.configs.recommended,
  {
    files: ["custom_components/grib_overlay/www/grib-overlay-card.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: ha.globals.card,
    },
    rules: ha.rules,
  },
];
