import { useQuery } from "@tanstack/react-query";

import { fetchCurrentRegime, fetchRegimeHistory } from "@/api/regime";

export const useCurrentRegime = () =>
  useQuery({ queryKey: ["regime", "current"], queryFn: fetchCurrentRegime });

export const useRegimeHistory = () =>
  useQuery({ queryKey: ["regime", "history"], queryFn: fetchRegimeHistory });
