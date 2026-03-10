"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { BusinessProposal } from "@/types/api";

export function usePendingProposals(sessionId: string | null, step?: string) {
  return useQuery({
    queryKey: ["proposals", "pending", sessionId, step],
    queryFn: () => {
      const params = step ? `?step=${step}` : "";
      return api.get<BusinessProposal[]>(
        `/sessions/${sessionId}/proposals/pending${params}`,
      );
    },
    enabled: !!sessionId,
    refetchInterval: 5000,
  });
}

export function useProposals(sessionId: string | null, step?: string) {
  return useQuery({
    queryKey: ["proposals", sessionId, step],
    queryFn: () => {
      const params = step ? `?step=${step}` : "";
      return api.get<BusinessProposal[]>(
        `/sessions/${sessionId}/proposals${params}`,
      );
    },
    enabled: !!sessionId,
  });
}

export function useProposalHistory(proposalId: string | null) {
  return useQuery({
    queryKey: ["proposal-history", proposalId],
    queryFn: () =>
      api.get<BusinessProposal[]>(`/proposals/${proposalId}/history`),
    enabled: !!proposalId,
  });
}

export function useApproveProposal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (proposalId: string) => {
      return api.post<BusinessProposal>(`/proposals/${proposalId}/approve`);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: ["proposals", "pending", data.session_id],
      });
      queryClient.invalidateQueries({
        queryKey: ["proposals", data.session_id],
      });
      queryClient.invalidateQueries({
        queryKey: ["session", data.session_id],
      });
    },
  });
}

export function useReviseProposal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      proposalId,
      feedback,
    }: {
      proposalId: string;
      feedback: string;
    }) => {
      return api.post<BusinessProposal>(`/proposals/${proposalId}/revise`, {
        feedback,
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: ["proposals", "pending", data.session_id],
      });
      queryClient.invalidateQueries({
        queryKey: ["proposals", data.session_id],
      });
    },
  });
}

export function useRejectProposal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      proposalId,
      feedback,
    }: {
      proposalId: string;
      feedback?: string;
    }) => {
      return api.post<BusinessProposal>(`/proposals/${proposalId}/reject`, {
        feedback: feedback || "",
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: ["proposals", "pending", data.session_id],
      });
      queryClient.invalidateQueries({
        queryKey: ["proposals", data.session_id],
      });
    },
  });
}

export function useSelectProposalOption() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      proposalId,
      selectedIndex,
      feedback,
    }: {
      proposalId: string;
      selectedIndex: number;
      feedback?: string;
    }) => {
      return api.post<BusinessProposal>(`/proposals/${proposalId}/select`, {
        selected_index: selectedIndex,
        feedback,
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: ["proposals", "pending", data.session_id],
      });
      queryClient.invalidateQueries({
        queryKey: ["proposals", data.session_id],
      });
    },
  });
}
