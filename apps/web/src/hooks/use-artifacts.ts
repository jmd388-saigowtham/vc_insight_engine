import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { Artifact } from "@/types/api";

export function useArtifacts(sessionId: string | null, step?: string) {
  return useQuery({
    queryKey: ["artifacts", sessionId, step],
    queryFn: () => {
      const query = step ? `?step=${step}` : "";
      return api.get<Artifact[]>(`/sessions/${sessionId}/artifacts${query}`);
    },
    enabled: !!sessionId,
  });
}
