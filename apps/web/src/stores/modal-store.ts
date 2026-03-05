import { create } from "zustand";
import type { CodeProposal } from "@/types/api";

interface ModalStore {
  isOpen: boolean;
  proposal: CodeProposal | null;
  openModal: (proposal: CodeProposal) => void;
  closeModal: () => void;
}

export const useModalStore = create<ModalStore>((set) => ({
  isOpen: false,
  proposal: null,
  openModal: (proposal) => set({ isOpen: true, proposal }),
  closeModal: () => set({ isOpen: false, proposal: null }),
}));
