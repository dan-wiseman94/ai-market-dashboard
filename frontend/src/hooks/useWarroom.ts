import { useMutation, useQuery } from "@tanstack/react-query";

import { conveneWarRoom, fetchWarRoomRuns } from "@/api/warroom";

export const useWarRoomRuns = () =>
  useQuery({ queryKey: ["warroom", "runs"], queryFn: fetchWarRoomRuns });

export const useConveneWarRoom = () => useMutation({ mutationFn: conveneWarRoom });
