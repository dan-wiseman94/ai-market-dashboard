import { useEffect, useState } from "react";
import { fetchHealth } from "@/api/client";

export type HealthState = "loading" | "ok" | "down";

export function useHealth(): HealthState {
  const [state, setState] = useState<HealthState>("loading");

  useEffect(() => {
    let cancelled = false;
    fetchHealth()
      .then((body) => {
        if (!cancelled) setState(body.status === "ok" ? "ok" : "down");
      })
      .catch(() => {
        if (!cancelled) setState("down");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
