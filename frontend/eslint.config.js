// For more info, see https://github.com/storybookjs/eslint-plugin-storybook#configuration-flat-config-format
import storybook from "eslint-plugin-storybook";

import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config({ ignores: ["dist", "node_modules", "src/api/schema.d.ts"] }, {
  extends: [js.configs.recommended, ...tseslint.configs.recommended],
  files: ["**/*.{ts,tsx}"],
  languageOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    globals: { ...globals.browser, ...globals.node },
  },
  plugins: {
    "react-hooks": reactHooks,
    "react-refresh": reactRefresh,
  },
  rules: {
    ...reactHooks.configs.recommended.rules,
    "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    // Complexity gate (mirrors the backend ruff C901 max-complexity=15). For components,
    // reduce by extracting subcomponents/handlers/hooks — not by raising the cap. A function
    // that's genuinely irreducible should carry an inline `// eslint-disable-next-line complexity`
    // with a reason.
    complexity: ["error", 15],
    "max-depth": ["error", 4],
  },
}, storybook.configs["flat/recommended"]);
