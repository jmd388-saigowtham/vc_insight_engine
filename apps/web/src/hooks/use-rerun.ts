"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { toast } from "sonner";

/**
 * Hook for triggering a pipeline rerun from a specific step.
 * Invalidates downstream steps and re-runs the pipeline.
 */
export function useRerun(sessionId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (step: string) =>
      api.post(`/sessions/${sessionId}/rerun/${step}`),
    onSuccess: (_data, step) => {
      toast.success(`Re-running pipeline from ${step}`);
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Rerun failed";
      if (message.includes("409") || message.includes("already running")) {
        toast.error("A pipeline step is already running. Please wait.");
      } else {
        toast.error(message);
      }
    },
  });
}
