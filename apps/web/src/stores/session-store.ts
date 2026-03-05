import { create } from "zustand";
import type { Session } from "@/types/session";

interface SessionStore {
  currentSessionId: string | null;
  session: Session | null;
  setSession: (session: Session) => void;
  setSessionId: (id: string | null) => void;
  clearSession: () => void;
}

export const useSessionStore = create<SessionStore>((set) => ({
  currentSessionId: null,
  session: null,
  setSession: (session) =>
    set({ session, currentSessionId: session.id }),
  setSessionId: (id) => set({ currentSessionId: id }),
  clearSession: () => set({ session: null, currentSessionId: null }),
}));
