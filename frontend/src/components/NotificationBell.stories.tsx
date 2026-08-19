import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { http, HttpResponse } from "msw";
import type { NotificationDTO } from "@/api/observer";
import { WebSocketProvider } from "@/realtime/WebSocketProvider";
import NotificationBell from "./NotificationBell";

// `listNotifications(false)` hits this path (with a `?limit=50` query MSW
// ignores for matching). The endpoint returns a bare NotificationDTO[] array.
const NOTIFICATIONS_URL = "/api/observer/notifications/";

const now = Date.now();
const minutesAgo = (m: number) => new Date(now - m * 60_000).toISOString();

const unreadFeed: NotificationDTO[] = [
  {
    id: 1,
    kind: "trigger",
    title: "Trigger fired: AAPL crossed $190",
    body: "price ≥ 190 on the 1m bar",
    link: "/triggers",
    meta: {},
    read_at: null,
    created_at: minutesAgo(2),
  },
  {
    id: 2,
    kind: "observer_done",
    title: "Observer run complete",
    body: "Morning watch finished for 6 tickers.",
    link: "/observer",
    meta: {},
    read_at: null,
    created_at: minutesAgo(18),
  },
  {
    id: 3,
    kind: "backup",
    title: "Nightly backup finished",
    body: "pg_dump rotated; 7 kept.",
    link: "/settings",
    meta: {},
    read_at: minutesAgo(120),
    created_at: minutesAgo(140),
  },
];

const allRead: NotificationDTO[] = unreadFeed.map((n) => ({ ...n, read_at: minutesAgo(200) }));

const meta = {
  title: "Layout/NotificationBell",
  component: NotificationBell,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "The TopNav notification bell. Self-fetches `/api/observer/notifications/` via react-query and subscribes to the `notifications` WebSocket channel; these stories mock the GET with MSW to exercise the unread badge, the all-read list, and the quiet empty state. A `WebSocketProvider` decorator supplies the `useWebSocket()` context the global preview does not.",
      },
    },
  },
  decorators: [
    (Story) => (
      <WebSocketProvider>
        <Story />
      </WebSocketProvider>
    ),
  ],
} satisfies Meta<typeof NotificationBell>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Two unread notifications — the copper count badge, then the open dropdown. */
export const Unread: Story = {
  args: {},
  parameters: {
    msw: { handlers: [http.get(NOTIFICATIONS_URL, () => HttpResponse.json(unreadFeed))] },
  },
  play: async ({ canvas, userEvent }) => {
    // The badge only appears once the query resolves (2 of 3 are unread).
    await expect(await canvas.findByText("2")).toBeVisible();
    await userEvent.click(canvas.getByRole("button", { name: "notifications" }));
    await expect(await canvas.findByText("Notifications")).toBeVisible();
    await expect(canvas.getByText("Trigger fired: AAPL crossed $190")).toBeVisible();
  },
};

/** Everything already read — no badge, list dimmed, no "unread" count anywhere. */
export const AllRead: Story = {
  args: {},
  parameters: {
    msw: { handlers: [http.get(NOTIFICATIONS_URL, () => HttpResponse.json(allRead))] },
  },
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: "notifications" }));
    await expect(await canvas.findByText("Observer run complete")).toBeVisible();
    await expect(canvas.queryByText(/unread/)).toBeNull();
  },
};

/** No notifications — the "Nothing to report." quiet-tape empty state. */
export const Empty: Story = {
  args: {},
  parameters: {
    msw: { handlers: [http.get(NOTIFICATIONS_URL, () => HttpResponse.json([]))] },
  },
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(canvas.getByRole("button", { name: "notifications" }));
    await expect(await canvas.findByText("Nothing to report.")).toBeVisible();
    await expect(canvas.getByText("The tape is quiet.")).toBeVisible();
  },
};
