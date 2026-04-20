import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const next = require("eslint-config-next/core-web-vitals");
const ts = require("eslint-config-next/typescript");

/** @type {import("eslint").Linter.Config[]} */
const eslintConfig = [
  ...next,
  ...ts,
  {
    ignores: ["eslint.quality.config.mjs"],
  },
  {
    rules: {
      "react-hooks/set-state-in-effect": "off",
      // CI strict mode: existing codebase contains many pragmatic `any` / unused vars.
      // Keep strict on errors, not on these warnings, and gradually tighten later.
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": "error",
      "react-hooks/exhaustive-deps": "error",
      "@next/next/no-img-element": "error",
    },
  },
  {
    files: ["app/policy-news/page.tsx"],
    rules: {
      "@next/next/no-img-element": "off",
    },
  },
];

export default eslintConfig;
