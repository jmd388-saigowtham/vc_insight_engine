"use client";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { useProposalStore } from "@/stores/proposal-store";
import { ProposalCard } from "./proposal-card";

export function ProposalModal() {
  const { isOpen, proposal, closeProposal } = useProposalStore();

  if (!proposal) return null;

  return (
    <Dialog open={isOpen} onOpenChange={() => closeProposal()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>AI Proposal — {proposal.step}</DialogTitle>
          <DialogDescription>
            Review the AI&apos;s plan before it proceeds.
          </DialogDescription>
        </DialogHeader>
        <ProposalCard
          proposal={proposal}
          onResolved={closeProposal}
        />
      </DialogContent>
    </Dialog>
  );
}
