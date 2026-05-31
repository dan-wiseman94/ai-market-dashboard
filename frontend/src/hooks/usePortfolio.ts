import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  closePosition,
  createPosition,
  deletePosition,
  listPositions,
  type ClosePositionBody,
  type CreatePositionBody,
  type ListPositionsParams,
} from "@/api/portfolio";

export function usePortfolioPositions(params?: ListPositionsParams) {
  return useQuery({
    queryKey: ["portfolio/positions", params ?? {}],
    queryFn: () => listPositions(params),
  });
}

export function useCreatePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreatePositionBody) => createPosition(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio/positions"] }),
  });
}

export function useClosePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: ClosePositionBody }) =>
      closePosition(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio/positions"] }),
  });
}

export function useDeletePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deletePosition(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolio/positions"] }),
  });
}
