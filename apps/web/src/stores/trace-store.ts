import { create } from "zustand";
import type { TraceEvent } from "@/types/event";

const MAX_EVENTS = 500;

interface TraceStore {
  events: TraceEvent[];
  isConnected: boolean;
  addEvent: (event: TraceEvent) => void;
  setEvents: (events: TraceEvent[]) => void;
  clearEvents: () => void;
  setConnected: (connected: boolean) => void;
}

export const useTraceStore = create<TraceStore>((set) => ({
  events: [],
  isConnected: false,
  addEvent: (event) =>
    set((state) => {
      const next = [...state.events, event];
      return { events: next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next };
    }),
  setEvents: (events) => set({ events: events.slice(-MAX_EVENTS) }),
  clearEvents: () => set({ events: [] }),
  setConnected: (connected) => set({ isConnected: connected }),
}));
