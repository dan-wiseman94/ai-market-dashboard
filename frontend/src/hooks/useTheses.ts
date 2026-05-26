import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  closeThesis,
  createThesis,
  deleteThesis,
  getThesis,
  listTheses,
  type CloseThesisBody,
  type CreateThesisBody,
} from "@/api/thesis";

export function useTheses() {
  return useQuery({
    queryKey: ["theses"],
    queryFn: listTheses,
  });
}

export function useThesis(id: number | null) {
  return useQuery({
    queryKey: ["theses", id],
    queryFn: () => getThesis(id!),
    enabled: id !== null,
  });
}

export function useCreateThesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateThesisBody) => createThesis(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["theses"] }),
  });
}

export function useCloseThesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: CloseThesisBody }) =>
      closeThesis(id, body),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["theses"] });
      qc.invalidateQueries({ queryKey: ["theses", id] });
    },
  });
}

export function useDeleteThesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteThesis(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["theses"] }),
  });
}
