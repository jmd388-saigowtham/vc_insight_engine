import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { Session, SessionCreate } from "@/types/session";

export function useSession(id: string | null) {
  return useQuery({
    queryKey: ["session", id],
    queryFn: () => api.get<Session>(`/sessions/${id}`),
    enabled: !!id,
  });
}

export function useCreateSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SessionCreate) =>
      api.post<Session>("/sessions", data),
    onSuccess: (session) => {
      queryClient.setQueryData(["session", session.id], session);
    },
  });
}

export function useUpdateSession(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<Session>) =>
      api.patch<Session>(`/sessions/${id}`, data),
    onSuccess: (session) => {
      queryClient.setQueryData(["session", session.id], session);
    },
  });
}

export function useSessions() {
  return useQuery({
    queryKey: ["sessions"],
    queryFn: () => api.get<Session[]>("/sessions"),
  });
}
