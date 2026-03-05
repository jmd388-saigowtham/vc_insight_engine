"use client";

import { useEffect, useRef } from "react";
import { createEventSource } from "@/lib/sse-client";
import { useTraceStore } from "@/stores/trace-store";
import type { TraceEvent } from "@/types/event";

export function useEventStream(sessionId: string | null) {
  const addEvent = useTraceStore((s) => s.addEvent);
  const setConnected = useTraceStore((s) => s.setConnected);
  const clearEvents = useTraceStore((s) => s.clearEvents);
  const sourceRef = useRef<{ close: () => void } | null>(null);

  useEffect(() => {
    if (!sessionId) return;

    clearEvents();

    sourceRef.current = createEventSource<TraceEvent>({
      url: `/sessions/${sessionId}/events/stream`,
      onEvent: (event) => addEvent(event),
      onOpen: () => setConnected(true),
      onError: () => setConnected(false),
    });

    return () => {
      sourceRef.current?.close();
      setConnected(false);
    };
  }, [sessionId, addEvent, setConnected, clearEvents]);
}
