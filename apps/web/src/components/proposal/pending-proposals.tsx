"use client";

import { usePendingProposals } from "@/hooks/use-proposals";
import { ProposalCard } from "./proposal-card";

interface PendingProposalsProps {
  sessionId: string;
  step?: string;
}

export function PendingProposals({ sessionId, step }: PendingProposalsProps) {
  const { data: proposals } = usePendingProposals(sessionId, step);

  if (!proposals || proposals.length === 0) return null;

  return (
    <div className="space-y-3">
      {proposals.map((p) => (
        <ProposalCard key={p.id} proposal={p} />
      ))}
    </div>
  );
}
