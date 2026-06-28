import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, waitFor } from "storybook/test";
import { ToastProvider, useToast, type ToastKind } from "../hooks/useToast";
import { Toasts } from "./Toasts";

// <Toasts/> is context-only (no props): it renders whatever lives in the
// ToastProvider's `toasts` state. This harness gives each story a button row
// that pushes toasts via `useToast().push`, rendered alongside the real stack.
const KINDS: ToastKind[] = ["info", "success", "error"];

function Trigger() {
  const { push } = useToast();
  return (
    <div className="flex gap-2">
      {KINDS.map((kind) => (
        <button key={kind} type="button" onClick={() => push({ kind, text: `${kind} message` })}>
          Push {kind}
        </button>
      ))}
    </div>
  );
}

const meta = {
  title: "Primitives/Toasts",
  component: Toasts,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Fixed bottom-right toast stack driven by ToastProvider context; each toast is tone-colored by kind (info/success/error) and click-to-dismiss.",
      },
    },
  },
  // <Toasts/> throws without a ToastProvider, which the global preview does not
  // supply. A long auto-dismiss keeps pushed toasts on screen for assertions.
  decorators: [
    (Story) => (
      <ToastProvider defaultDurationMs={1_000_000}>
        <Trigger />
        <Story />
      </ToastProvider>
    ),
  ],
} satisfies Meta<typeof Toasts>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Pushing an info toast renders its text in the bottom-right stack. */
export const Default: Story = {
  args: {},
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(canvas.getByRole("button", { name: /push info/i }));
    await expect(await canvas.findByText("info message")).toBeVisible();
  },
};

/** One toast per kind; each carries its own `toast-<kind>` testid. */
export const AllKinds: Story = {
  args: {},
  play: async ({ canvas, userEvent }) => {
    for (const kind of KINDS) {
      await userEvent.click(canvas.getByRole("button", { name: new RegExp(`push ${kind}`, "i") }));
    }
    await expect(await canvas.findByTestId("toast-info")).toBeVisible();
    await expect(await canvas.findByTestId("toast-success")).toBeVisible();
    await expect(await canvas.findByTestId("toast-error")).toBeVisible();
  },
};

/** Clicking a toast dismisses it, removing it from the stack. */
export const ClickToDismiss: Story = {
  args: {},
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(canvas.getByRole("button", { name: /push success/i }));
    const toast = await canvas.findByText("success message");
    await expect(toast).toBeVisible();
    await userEvent.click(toast);
    await waitFor(() => expect(canvas.queryByText("success message")).toBeNull());
  },
};
