import { useQuery } from "@tanstack/react-query";
import { fetchSystemSettings } from "@/api/settings";

export const useSystemSettings = () =>
  useQuery({
    queryKey: ["system-settings"],
    queryFn: fetchSystemSettings,
    staleTime: 30_000,
  });
