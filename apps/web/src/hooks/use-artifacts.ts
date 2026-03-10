import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { Artifact, DatasetEntry } from "@/types/api";

export function useArtifacts(
  sessionId: string | null,
  step?: string,
  options?: { refetchInterval?: number | false },
) {
  return useQuery({
    queryKey: ["artifacts", sessionId, step],
    queryFn: () => {
      const query = step ? `?step=${step}` : "";
      return api.get<Artifact[]>(`/sessions/${sessionId}/artifacts${query}`);
    },
    enabled: !!sessionId,
    refetchInterval: options?.refetchInterval,
  });
}

export function useDatasets(sessionId: string | null) {
  return useQuery({
    queryKey: ["datasets", sessionId],
    queryFn: () =>
      api.get<DatasetEntry[]>(`/sessions/${sessionId}/datasets`),
    enabled: !!sessionId,
  });
}
