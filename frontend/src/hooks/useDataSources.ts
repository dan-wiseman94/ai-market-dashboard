import { useQuery } from "@tanstack/react-query";
import { fetchDataSources } from "@/api/dataSources";

export const useDataSources = () =>
  useQuery({
    queryKey: ["data-sources"],
    queryFn: fetchDataSources,
    staleTime: 10_000,
  });
