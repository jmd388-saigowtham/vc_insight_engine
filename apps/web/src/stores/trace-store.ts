import { create } from "zustand";
import type { TraceEvent } from "@/types/event";

interface TraceStore {
  events: TraceEvent[];
  isConnected: boolean;
  addEvent: (event: TraceEvent) => void;
  clearEvents: () => void;
  setConnected: (connected: boolean) => void;
}

export const useTraceStore = create<TraceStore>((set) => ({
  events: [],
  isConnected: false,
  addEvent: (event) =>
    set((state) => ({ events: [...state.events, event] })),
  clearEvents: () => set({ events: [] }),
  setConnected: (connected) => set({ isConnected: connected }),
}));
