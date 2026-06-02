import { useMutation, useQuery } from "@tanstack/react-query";

import { conveneWarRoom, fetchWarRoomRun, fetchWarRoomRuns } from "@/api/warroom";

export const useWarRoomRuns = () =>
  useQuery({ queryKey: ["warroom", "runs"], queryFn: fetchWarRoomRuns });

export const useWarRoomRun = (id: number) =>
  useQuery({
    queryKey: ["warroom", "run", id],
    queryFn: () => fetchWarRoomRun(id),
    // While the debate is running, poll so completed persona lanes + the final
    // verdict fill in (token-level streaming is layered on via useWarRoomLive).
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1500 : false),
  });

export const useConveneWarRoom = () => useMutation({ mutationFn: conveneWarRoom });
