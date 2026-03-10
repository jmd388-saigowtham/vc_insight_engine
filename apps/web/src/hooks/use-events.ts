"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { createEventSource } from "@/lib/sse-client";
import { useTraceStore } from "@/stores/trace-store";
import { useModalStore } from "@/stores/modal-store";
import { useProposalStore } from "@/stores/proposal-store";
import type { TraceEvent } from "@/types/event";
import type { CodeProposal, CodeContext, BusinessProposal } from "@/types/api";
import { api } from "@/lib/api-client";

export function useEventStream(sessionId: string | null) {
  const addEvent = useTraceStore((s) => s.addEvent);
  const setConnected = useTraceStore((s) => s.setConnected);
  const setEvents = useTraceStore((s) => s.setEvents);
  const queryClient = useQueryClient();
  const sourceRef = useRef<{ close: () => void } | null>(null);
  const knownIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!sessionId) return;

    let cancelled = false;

    async function init() {
      // 1. Fetch historical events
      try {
        const history = await api.get<TraceEvent[]>(
          `/sessions/${sessionId}/events?limit=200`
        );
        if (cancelled) return;
        // API returns DESC order, reverse for chronological
        const chronological = [...history].reverse();
        setEvents(chronological);
        // Build dedup set
        knownIdsRef.current = new Set(chronological.map((e) => e.id));
      } catch {
        // Fall back to empty — SSE will populate
        if (cancelled) return;
        knownIdsRef.current = new Set();
      }

      if (cancelled) return;

      // 2. Start SSE connection
      sourceRef.current = createEventSource<TraceEvent>({
        url: `/sessions/${sessionId}/events/stream`,
        onEvent: (event) => {
          // Dedup: skip events we already have from history
          if (knownIdsRef.current.has(event.id)) return;
          knownIdsRef.current.add(event.id);

          addEvent(event);

          // Auto-open code approval modal
          if (event.event_type === "CODE_PROPOSED" && event.payload) {
            const payload = event.payload as {
              proposal_id?: string;
              code?: string;
              language?: string;
              description?: string;
              node_name?: string;
              context?: CodeContext;
            };
            if (payload.proposal_id && payload.code) {
              const proposal: CodeProposal = {
                id: payload.proposal_id,
                session_id: sessionId!,
                step: event.step || payload.node_name || "",
                language: payload.language || "python",
                code: payload.code,
                description: payload.description || "",
                status: "pending",
                node_name: payload.node_name,
                context: payload.context,
              };
              const context = payload.context ?? null;
              useModalStore.getState().openModal(proposal, context);
            }
          }

          // Auto-open business proposal modal
          if (event.event_type === "PROPOSAL_CREATED" && event.payload) {
            const payload = event.payload as {
              proposal_id?: string;
              proposal_type?: string;
              version?: number;
              summary?: string;
            };
            if (payload.proposal_id) {
              // Fetch the full proposal then open modal
              api
                .get<BusinessProposal>(`/proposals/${payload.proposal_id}`)
                .then((proposal) => {
                  useProposalStore.getState().openProposal(proposal);
                })
                .catch(() => {
                  // If fetch fails, build a minimal proposal from event data
                  useProposalStore.getState().openProposal({
                    id: payload.proposal_id!,
                    session_id: sessionId!,
                    step: event.step || "",
                    proposal_type: payload.proposal_type || "generic",
                    status: "pending",
                    version: payload.version ?? 1,
                    plan: null,
                    summary: payload.summary || null,
                    ai_reasoning: null,
                    alternatives: null,
                    user_feedback: null,
                    parent_id: null,
                    resolved_at: null,
                    created_at: new Date().toISOString(),
                  });
                });
            }
            // Also refresh proposals queries
            queryClient.invalidateQueries({
              queryKey: ["proposals", "pending", sessionId],
            });
          }

          // Refresh proposals on proposal state changes
          if (
            event.event_type === "PROPOSAL_APPROVED" ||
            event.event_type === "PROPOSAL_REVISED" ||
            event.event_type === "PROPOSAL_REJECTED"
          ) {
            queryClient.invalidateQueries({
              queryKey: ["proposals", "pending", sessionId],
            });
            queryClient.invalidateQueries({
              queryKey: ["proposals", sessionId],
            });
          }

          // Refresh session data and step states on step state changes
          if (
            event.event_type === "STEP_STALE" ||
            event.event_type === "STEP_START" ||
            event.event_type === "STEP_END" ||
            event.event_type === "STAGE_MARKED_STALE" ||
            event.event_type === "STAGE_RUNNING" ||
            event.event_type === "STAGE_DONE"
          ) {
            queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
            queryClient.invalidateQueries({ queryKey: ["step-states", sessionId] });
          }
        },
        onOpen: () => setConnected(true),
        onError: () => setConnected(false),
      });
    }

    init();

    return () => {
      cancelled = true;
      sourceRef.current?.close();
      setConnected(false);
    };
  }, [sessionId, addEvent, setConnected, setEvents, queryClient]);
}
