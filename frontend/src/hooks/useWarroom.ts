import { useMutation, useQuery } from "@tanstack/react-query";

import { conveneWarRoom, fetchWarRoomRun, fetchWarRoomRuns } from "@/api/warroom";

export const useWarRoomRuns = () =>
  useQuery({ queryKey: ["warroom", "runs"], queryFn: fetchWarRoomRuns });

export const useWarRoomRun = (id: number) =>
  useQuery({ queryKey: ["warroom", "run", id], queryFn: () => fetchWarRoomRun(id) });

export const useConveneWarRoom = () => useMutation({ mutationFn: conveneWarRoom });
