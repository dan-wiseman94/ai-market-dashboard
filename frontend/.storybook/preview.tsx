import type { Preview } from "@storybook/react-vite";
import "../src/styles/globals.css";
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { INITIAL_VIEWPORTS } from "storybook/viewport";
import { initialize, mswLoader } from "msw-storybook-addon";

// Start MSW once. Unhandled requests pass through, so the prop-driven stories
// that make no network calls are unaffected; data stories declare their own
// handlers via `parameters.msw.handlers`.
initialize({ onUnhandledRequest: "bypass" });

const preview: Preview = {
  // Generate a Docs page for every component.
  tags: ["autodocs"],

  globalTypes: {
    theme: {
      description: "Canvas theme",
      toolbar: {
        title: "Theme",
        icon: "contrast",
        items: [
          { value: "dark", title: "Dark" },
          { value: "light", title: "Light" },
        ],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: { theme: "dark" },

  parameters: {
    layout: "padded",
    controls: {
      matchers: { color: /(background|color)$/i, date: /Date$/i },
      expanded: true,
    },
    // 'todo' surfaces a11y violations in the test UI without failing the run.
    a11y: { test: "todo" },
    // The Theme toolbar owns the canvas background, so disable the separate switcher.
    backgrounds: { disable: true },
    viewport: { options: INITIAL_VIEWPORTS },
    options: {
      storySort: {
        method: "alphabetical",
        order: ["Primitives", "Layout", "Thread", "Market", "Snapshot", "Observer", "Content", "*"],
      },
    },
  },

  loaders: [mswLoader],

  decorators: [
    // Real-ish provider tree: a fresh QueryClient per story (so cached data
    // never leaks between stories) plus a router for <Link>-using components.
    (Story) => {
      const [client] = useState(
        () =>
          new QueryClient({
            defaultOptions: {
              queries: { retry: false, refetchOnWindowFocus: false, gcTime: Infinity },
            },
          }),
      );
      return (
        <QueryClientProvider client={client}>
          <MemoryRouter>
            <Story />
          </MemoryRouter>
        </QueryClientProvider>
      );
    },
    // Theme canvas: ink-950 (the app's dark default) or a light paper canvas,
    // driven by the Theme toolbar. Also settles entrance animations instantly so
    // the vitest browser lane isn't racing `.ledger-reveal` opacity (0 → 1).
    (Story, context) => {
      const dark = (context.globals.theme ?? "dark") !== "light";
      return (
        <div
          className={dark ? "dark" : ""}
          style={{
            background: dark ? "#0b0d12" : "#f5f6fb",
            minHeight: "100vh",
            padding: "2rem",
          }}
        >
          <style>{`*, *::before, *::after { animation-duration: 0s !important; animation-delay: 0s !important; transition-duration: 0s !important; }`}</style>
          <Story />
        </div>
      );
    },
  ],
};

export default preview;
