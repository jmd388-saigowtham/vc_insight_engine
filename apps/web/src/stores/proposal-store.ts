import { create } from "zustand";
import type { BusinessProposal } from "@/types/api";

interface ProposalStore {
  isOpen: boolean;
  proposal: BusinessProposal | null;
  openProposal: (proposal: BusinessProposal) => void;
  closeProposal: () => void;
}

export const useProposalStore = create<ProposalStore>((set) => ({
  isOpen: false,
  proposal: null,
  openProposal: (proposal) => set({ isOpen: true, proposal }),
  closeProposal: () => set({ isOpen: false, proposal: null }),
}));
