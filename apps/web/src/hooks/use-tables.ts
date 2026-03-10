import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, uploadFile } from "@/lib/api-client";
import type { UploadedFile, TableProfile, ColumnProfile } from "@/types/api";

export interface SheetInfo {
  name: string;
  index: number;
}

interface ListSheetsResponse {
  sheets: SheetInfo[];
  is_multi_sheet: boolean;
}

interface FileListResponse {
  files: UploadedFile[];
  total: number;
}

export function useFiles(sessionId: string | null) {
  return useQuery({
    queryKey: ["files", sessionId],
    queryFn: async () => {
      const res = await api.get<FileListResponse>(`/sessions/${sessionId}/files`);
      return res.files;
    },
    enabled: !!sessionId,
  });
}

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
      queryClient.invalidateQueries({ queryKey: ["files", sessionId] });
      queryClient.invalidateQueries({ queryKey: ["tables", sessionId] });
    },
  });
}

export function useListSheets(fileId: string | null) {
  return useQuery({
    queryKey: ["sheets", fileId],
    queryFn: () => api.get<ListSheetsResponse>(`/files/${fileId}/sheets`),
    enabled: !!fileId,
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
