import type { StorybookConfig } from '@storybook/react-vite';

const config: StorybookConfig = {
  // Serve public/ so MSW's mockServiceWorker.js is reachable at /mockServiceWorker.js.
  "staticDirs": ["../public"],
  "stories": [
    "../src/**/*.mdx",
    "../src/**/*.stories.@(js|jsx|mjs|ts|tsx)"
  ],
  "addons": [
    "@storybook/addon-vitest",
    "@storybook/addon-a11y",
    "@storybook/addon-docs",
    "@storybook/addon-mcp"
  ],
  // Storybook 10.4 turned on git-diff change detection ("modified/affected
  // stories") by default. It can't work in the storybook container — only
  // ./frontend is mounted (/app), never the repo-root .git — so it logs
  // "Change detection unavailable" on every boot. We don't use it; disabling
  // the feature skips the git probe (and the warning) entirely.
  "features": {
    "changeDetection": false
  },
  "framework": "@storybook/react-vite"
};
export default config;