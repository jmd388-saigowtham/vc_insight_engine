import { create } from "zustand";
import type { CodeProposal, CodeContext } from "@/types/api";

interface ModalStore {
  isOpen: boolean;
  proposal: CodeProposal | null;
  context: CodeContext | null;
  openModal: (proposal: CodeProposal, context?: CodeContext | null) => void;
  closeModal: () => void;
}

export const useModalStore = create<ModalStore>((set) => ({
  isOpen: false,
  proposal: null,
  context: null,
  openModal: (proposal, context) => set({ isOpen: true, proposal, context: context ?? null }),
  closeModal: () => set({ isOpen: false, proposal: null, context: null }),
}));
