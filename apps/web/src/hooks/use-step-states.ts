import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

interface StepStatesResponse {
  step_states: Record<string, string>;
}

export function useStepStates(sessionId: string | null) {
  return useQuery({
    queryKey: ["step-states", sessionId],
    queryFn: () =>
      api.get<StepStatesResponse>(`/sessions/${sessionId}/step-states`),
    enabled: !!sessionId,
    refetchInterval: 5000,
    select: (data) => data.step_states,
  });
}
