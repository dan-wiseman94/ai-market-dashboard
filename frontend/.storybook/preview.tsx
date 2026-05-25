import type { Preview } from "@storybook/react-vite";
import "../src/styles/globals.css";

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },

    a11y: {
      // 'todo' - show a11y violations in the test UI only
      // 'error' - fail CI on a11y violations
      // 'off' - skip a11y checks entirely
      test: "todo",
    },

    // The app's theme lives on `html.dark` with an ink-950 canvas; the
    // decorator below reproduces that so components render in context.
    // Disable the toolbar background switcher to keep the dark canvas authoritative.
    backgrounds: { disable: true },
  },
  decorators: [
    (Story) => (
      <div
        className="dark"
        style={{ background: "#0b0d12", minHeight: "100vh", padding: "2rem" }}
      >
        {/* Settle entrance animations (e.g. .ledger-reveal starts at opacity 0)
            instantly so components are visible immediately — keeps the vitest
            browser lane deterministic without waiting on 520ms reveals. */}
        <style>{`*, *::before, *::after { animation-duration: 0s !important; animation-delay: 0s !important; transition-duration: 0s !important; }`}</style>
        <Story />
      </div>
    ),
  ],
};

export default preview;
