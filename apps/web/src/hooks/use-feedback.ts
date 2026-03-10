"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { UserFeedbackEntry } from "@/types/api";

export function useFeedback(sessionId: string | null, step?: string) {
  return useQuery({
    queryKey: ["feedback", sessionId, step],
    queryFn: () => {
      const params = step ? `?step=${step}` : "";
      return api.get<UserFeedbackEntry[]>(
        `/sessions/${sessionId}/feedback${params}`,
      );
    },
    enabled: !!sessionId,
  });
}

export function useSubmitFeedback(sessionId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      message,
      step,
    }: {
      message: string;
      step?: string;
    }) => {
      return api.post<UserFeedbackEntry>(
        `/sessions/${sessionId}/feedback`,
        { message, step },
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["feedback", sessionId],
      });
    },
  });
}
