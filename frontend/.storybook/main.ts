import type { StorybookConfig } from '@storybook/react-vite';

const config: StorybookConfig = {
  // Serve public/ so MSW's mockServiceWorker.js is reachable at /mockServiceWorker.js.
  "staticDirs": ["../public"],
  "stories": [
    "../src/**/*.mdx",
    "../src/**/*.stories.@(js|jsx|mjs|ts|tsx)"
  ],
  "addons": [
    "@chromatic-com/storybook",
    "@storybook/addon-vitest",
    "@storybook/addon-a11y",
    "@storybook/addon-docs",
    "@storybook/addon-mcp"
  ],
  "framework": "@storybook/react-vite"
};
export default config;