/**
 * The one frame NotificationConsumer sends on `/ws/notifications/`
 * (apps/observer/consumers.py): the serialized Notification row wrapped in a
 * `notification.event` envelope. Seq-less — this channel has no replay buffer,
 * so every frame dispatches unconditionally.
 */
import type { NotificationDTO } from "@/api/observer";

export type NotificationWsMsg = {
  type: "notification.event";
  payload: NotificationDTO;
};
