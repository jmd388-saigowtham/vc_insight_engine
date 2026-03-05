import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, uploadFile } from "@/lib/api-client";
import type { TableProfile, ColumnProfile } from "@/types/api";

export function useTables(sessionId: string | null) {
  return useQuery({
    queryKey: ["tables", sessionId],
    queryFn: () => api.get<TableProfile[]>(`/sessions/${sessionId}/tables`),
    enabled: !!sessionId,
  });
}

export function useUploadFile(sessionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      file,
      onProgress,
    }: {
      file: File;
      onProgress?: (pct: number) => void;
    }) => uploadFile(`/sessions/${sessionId}/upload`, file, onProgress),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tables", sessionId] });
    },
  });
}

export function useUpdateColumnDescription() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      columnId,
      description,
    }: {
      columnId: string;
      description: string;
    }) =>
      api.patch<ColumnProfile>(`/columns/${columnId}/description`, {
        description,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tables"] });
    },
  });
}
