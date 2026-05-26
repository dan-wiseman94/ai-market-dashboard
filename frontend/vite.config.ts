/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { storybookTest } from "@storybook/addon-vitest/vitest-plugin";
import { playwright } from "@vitest/browser-playwright";

// Storybook stories run in a real browser via Playwright. The frontend image is
// Alpine, so Playwright can't use its bundled Chromium — point it at the system
// chromium installed in Dockerfile.dev (CHROMIUM_BIN) and disable the sandbox
// since we run unprivileged inside the container.
const storybookBrowser = playwright({
  launchOptions: {
    executablePath: process.env.CHROMIUM_BIN || undefined,
    chromiumSandbox: false,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  },
});

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    allowedHosts: ["frontend", "localhost", "127.0.0.1"],
    proxy: {
      "/api": {
        target: "http://web:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://web:8000",
        ws: true,
        changeOrigin: true,
      },
    },
  },
  test: {
    env: {
      VITE_API_BASE_URL: "",
    },
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/__tests__/**", "src/main.tsx", "src/vite-env.d.ts", "src/router.tsx"],
    },
    projects: [
      {
        // Existing jsdom unit suite — `vitest --project unit` (the default
        // `pnpm test` still runs this lane).
        extends: true,
        test: {
          name: "unit",
          globals: true,
          environment: "jsdom",
          setupFiles: ["./src/__tests__/setup.ts"],
          include: ["src/**/*.{test,spec}.{ts,tsx}"],
        },
      },
      {
        // Storybook stories as browser tests — `vitest --project storybook`.
        extends: true,
        plugins: [
          storybookTest({
            configDir: path.join(__dirname, ".storybook"),
            storybookScript: "pnpm run storybook --ci",
          }),
        ],
        test: {
          name: "storybook",
          browser: {
            enabled: true,
            provider: storybookBrowser,
            headless: true,
            instances: [{ browser: "chromium" }],
          },
          setupFiles: ["./.storybook/vitest.setup.ts"],
        },
      },
    ],
  },
});
