import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "@/api/client";

export type HealthState = "loading" | "ok" | "down";

// Polls so the connection indicator recovers when the backend comes back,
// instead of latching whatever state it saw at mount.
export function useHealth(): HealthState {
  const { data, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 10_000,
    retry: false,
  });
  if (isError) return "down";
  if (!data) return "loading";
  return data.status === "ok" ? "ok" : "down";
}
