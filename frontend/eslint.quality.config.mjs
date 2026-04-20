import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const next = require("eslint-config-next/core-web-vitals");
const ts = require("eslint-config-next/typescript");

/** @type {import("eslint").Linter.Config[]} */
const qualityConfig = [
  ...next,
  ...ts,
  {
    rules: {
      // Keep aligned with `eslint.config.mjs`, but re-enable quality signals.
      // This command is informative and should not block CI unless you decide so later.
      "react-hooks/set-state-in-effect": "off",

      // Gradual cleanup: surface `any` usage without blocking CI.
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-unused-vars": "warn",
      "react-hooks/exhaustive-deps": "warn",
      "@next/next/no-img-element": "warn",

    },
  },
];

export default qualityConfig;

