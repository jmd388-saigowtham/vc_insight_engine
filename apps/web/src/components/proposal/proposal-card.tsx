"use client";

import { useState } from "react";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  useApproveProposal,
  useReviseProposal,
  useRejectProposal,
} from "@/hooks/use-proposals";
import { api } from "@/lib/api-client";
import { toast } from "sonner";
import {
  CheckCircle,
  XCircle,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  Loader2,
  Clock,
  Lightbulb,
} from "lucide-react";
import type { BusinessProposal } from "@/types/api";
import { MergePlanView } from "./plan-renderers/merge-plan-view";
import { TargetSelectionView } from "./plan-renderers/target-selection-view";
import { FeatureSelectionView } from "./plan-renderers/feature-selection-view";
import { PreprocessingView } from "./plan-renderers/preprocessing-view";
import { ModelSelectionView } from "./plan-renderers/model-selection-view";
import { ThresholdView } from "./plan-renderers/threshold-view";
import { EdaPlanView } from "./plan-renderers/eda-plan-view";
import { HypothesisBatchView } from "./plan-renderers/hypothesis-batch-view";
import { FeatureEngView } from "./plan-renderers/feature-eng-view";
import { GenericPlanView } from "./plan-renderers/generic-plan-view";

interface ProposalCardProps {
  proposal: BusinessProposal;
  onResolved?: () => void;
}

const STATUS_STYLES: Record<string, { color: string; label: string }> = {
  pending: { color: "bg-amber-500", label: "Pending" },
  approved: { color: "bg-green-500", label: "Approved" },
  revised: { color: "bg-blue-500", label: "Revised" },
  rejected: { color: "bg-red-500", label: "Rejected" },
};

function PlanRenderer({ proposalType, plan }: { proposalType: string; plan: Record<string, unknown> }) {
  switch (proposalType) {
    case "merge_plan":
      return <MergePlanView plan={plan} />;
    case "target_selection":
      return <TargetSelectionView plan={plan} />;
    case "feature_selection":
      return <FeatureSelectionView plan={plan} />;
    case "preprocessing":
      return <PreprocessingView plan={plan} />;
    case "model_selection":
      return <ModelSelectionView plan={plan} />;
    case "threshold_plan":
      return <ThresholdView plan={plan} />;
    case "eda_plan":
      return <EdaPlanView plan={plan} />;
    case "hypothesis_batch":
      return <HypothesisBatchView plan={plan} />;
    case "feature_eng":
      return <FeatureEngView plan={plan} />;
    default:
      return <GenericPlanView plan={plan} />;
  }
}

export function ProposalCard({ proposal, onResolved }: ProposalCardProps) {
  const [showReasoning, setShowReasoning] = useState(false);
  const [showRevisionInput, setShowRevisionInput] = useState(false);
  const [feedback, setFeedback] = useState("");

  const approveMutation = useApproveProposal();
  const reviseMutation = useReviseProposal();
  const rejectMutation = useRejectProposal();

  const isPending = proposal.status === "pending";
  const isLoading =
    approveMutation.isPending ||
    reviseMutation.isPending ||
    rejectMutation.isPending;

  const statusStyle = STATUS_STYLES[proposal.status] ?? STATUS_STYLES.pending;

  async function resumePipeline() {
    try {
      await api.post(`/sessions/${proposal.session_id}/resume`, {
        proposal_id: proposal.id,
        proposal_type: "business",
      });
    } catch {
      // Resume is best-effort
    }
  }

  async function handleApprove() {
    try {
      await approveMutation.mutateAsync(proposal.id);
      toast.success("Proposal approved");
      await resumePipeline();
      onResolved?.();
    } catch {
      toast.error("Failed to approve proposal");
    }
  }

  async function handleRevise() {
    if (!feedback.trim()) {
      toast.error("Please provide feedback for the AI");
      return;
    }
    try {
      await reviseMutation.mutateAsync({
        proposalId: proposal.id,
        feedback: feedback.trim(),
      });
      toast.success("Revision requested");
      setFeedback("");
      setShowRevisionInput(false);
      await resumePipeline();
      onResolved?.();
    } catch {
      toast.error("Failed to request revision");
    }
  }

  async function handleReject() {
    try {
      await rejectMutation.mutateAsync({
        proposalId: proposal.id,
        feedback: feedback.trim() || undefined,
      });
      toast.info("Proposal rejected");
      setFeedback("");
      setShowRevisionInput(false);
      await resumePipeline();
      onResolved?.();
    } catch {
      toast.error("Failed to reject proposal");
    }
  }

  return (
    <Card className="border-l-4 border-l-primary">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            AI Proposal: {proposal.proposal_type.replace(/_/g, " ")}
          </CardTitle>
          <div className="flex items-center gap-2">
            {proposal.version > 1 && (
              <Badge variant="outline" className="text-[10px]">
                v{proposal.version}
              </Badge>
            )}
            <Badge className={`${statusStyle.color} text-white text-[10px]`}>
              {statusStyle.label}
            </Badge>
          </div>
        </div>
        {proposal.summary && (
          <p className="text-xs text-muted-foreground mt-1">{proposal.summary}</p>
        )}
      </CardHeader>

      <CardContent className="pb-2 space-y-3">
        {proposal.plan && (
          <PlanRenderer
            proposalType={proposal.proposal_type}
            plan={proposal.plan}
          />
        )}

        {proposal.ai_reasoning && (
          <div>
            <button
              onClick={() => setShowReasoning(!showReasoning)}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              <Lightbulb className="h-3 w-3 text-purple-500" />
              AI Reasoning
              {showReasoning ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </button>
            {showReasoning && (
              <p className="mt-1 text-xs text-muted-foreground italic border-l-2 border-purple-300 pl-2">
                {proposal.ai_reasoning}
              </p>
            )}
          </div>
        )}

        {showRevisionInput && isPending && (
          <div className="flex items-end gap-2 rounded-md border bg-muted/30 p-3">
            <Textarea
              placeholder="Describe what the AI should change..."
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              className="min-h-[60px] flex-1 text-xs"
              disabled={isLoading}
            />
            <div className="flex flex-col gap-1">
              <Button
                size="sm"
                onClick={handleRevise}
                disabled={isLoading}
                className="bg-amber-600 hover:bg-amber-700"
              >
                {reviseMutation.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  "Send"
                )}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setShowRevisionInput(false);
                  setFeedback("");
                }}
                disabled={isLoading}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
      </CardContent>

      {isPending && (
        <CardFooter className="gap-2 pt-2">
          <Button
            variant="destructive"
            size="sm"
            onClick={handleReject}
            disabled={isLoading}
          >
            <XCircle className="mr-1 h-3.5 w-3.5" />
            Reject
          </Button>
          {!showRevisionInput && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowRevisionInput(true)}
              disabled={isLoading}
            >
              <MessageSquare className="mr-1 h-3.5 w-3.5" />
              Request Changes
            </Button>
          )}
          <Button
            size="sm"
            onClick={handleApprove}
            disabled={isLoading}
            className="ml-auto bg-green-600 hover:bg-green-700"
          >
            {approveMutation.isPending ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <CheckCircle className="mr-1 h-3.5 w-3.5" />
            )}
            Approve
          </Button>
        </CardFooter>
      )}
    </Card>
  );
}
