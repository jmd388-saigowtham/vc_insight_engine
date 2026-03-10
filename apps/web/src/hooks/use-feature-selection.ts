import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

interface Feature {
  name: string;
  dtype: string;
  null_pct: number;
  unique_count: number;
  importance: number;
  selected: boolean;
  reasoning?: string;
  leakage_risk?: boolean;
  source?: string;
}

interface FeatureSelectionData {
  target_column: string;
  features: Feature[];
  selected_features: string[];
}

export function useFeatureSelection(sessionId: string) {
  return useQuery({
    queryKey: ["feature-selection", sessionId],
    queryFn: () => api.get<FeatureSelectionData>(`/sessions/${sessionId}/feature-selection`),
    enabled: !!sessionId,
  });
}

export function useUpdateFeatureSelection(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { target_column: string; selected_features: string[] }) =>
      api.patch(`/sessions/${sessionId}/feature-selection`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feature-selection", sessionId] });
    },
  });
}
