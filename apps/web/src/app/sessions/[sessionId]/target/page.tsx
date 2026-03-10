"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useWizardNavigation } from "@/hooks/use-wizard-navigation";
import { useStepStates } from "@/hooks/use-step-states";
import { usePendingProposals, useReviseProposal, useApproveProposal } from "@/hooks/use-proposals";
import { useTraceStore } from "@/stores/trace-store";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { StepStatusBanner } from "@/components/step-status-banner";
import { ArrowRight, Target, Loader2, Brain, CircleDot, MessageSquare, Sparkles } from "lucide-react";
import { PendingProposals } from "@/components/proposal/pending-proposals";
import { toast } from "sonner";

interface TargetConfig {
  target_variable: string;
  features: { name: string; included: boolean; importance: number }[];
  preview: Record<string, unknown>[];
  ai_explanation?: string;
  alternatives?: { name: string; reason: string }[];
}

export default function TargetPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const { navigateToNext, isPending } = useWizardNavigation("target");
  const { data: stepStates } = useStepStates(sessionId);
  const { data: pendingProposals } = usePendingProposals(sessionId, "target_id");
  const reviseProposal = useReviseProposal();
  const approveProposal = useApproveProposal();
  const queryClient = useQueryClient();
  const events = useTraceStore((s) => s.events);
  const [revisionText, setRevisionText] = useState("");
  const [showRevisionInput, setShowRevisionInput] = useState(false);

  const targetState = stepStates?.target_id;
  const hasPendingProposals = (pendingProposals?.length ?? 0) > 0;
  const isRunning = targetState === "RUNNING";

  const { data: config, isLoading } = useQuery({
    queryKey: ["target", sessionId],
    queryFn: () =>
      api.get<TargetConfig>(`/sessions/${sessionId}/target`),
    refetchInterval: targetState === "RUNNING" ? 5000 : false,
  });

  // Extract AI reasoning for target selection from trace events
  const targetReasoningEvents = events.filter(
    (e) =>
      (e.event_type === "AI_REASONING" || e.event_type === "DECISION") &&
      e.step === "target_id",
  );
  const aiExplanationFromEvents = targetReasoningEvents
    .map((e) => {
      const payload = e.payload as Record<string, unknown>;
      return (
        (payload.reasoning as string) ??
        (payload.message as string) ??
        (payload.decision as string) ??
        null
      );
    })
    .filter(Boolean) as string[];

  const aiExplanation =
    config?.ai_explanation ||
    (aiExplanationFromEvents.length > 0
      ? aiExplanationFromEvents.join(" ")
      : null);

  const alternatives = config?.alternatives ?? [];

  async function handleConfirm() {
    if (hasPendingProposals) {
      const proposal = pendingProposals![0];
      try {
        await approveProposal.mutateAsync(proposal.id);
        await api.post(`/sessions/${sessionId}/resume`, {
          proposal_id: proposal.id,
          proposal_type: "business",
        });
      } catch {
        toast.error("Failed to approve proposal");
        return;
      }
    }
    navigateToNext("feature-selection", {
      target_column: config?.target_variable ?? undefined,
    });
  }

  function handleRequestRevision() {
    if (!revisionText.trim() || !pendingProposals?.[0]) return;
    reviseProposal.mutate(
      { proposalId: pendingProposals[0].id, feedback: revisionText.trim() },
      {
        onSuccess: () => {
          toast.success("Revision requested — AI is re-evaluating the target");
          setRevisionText("");
          setShowRevisionInput(false);
          queryClient.invalidateQueries({ queryKey: ["proposals", "pending", sessionId] });
          queryClient.invalidateQueries({ queryKey: ["target", sessionId] });
        },
        onError: () => toast.error("Failed to submit revision"),
      },
    );
  }

  async function handleSuggestAlternative(altName: string) {
    const proposal = pendingProposals?.[0];
    if (proposal) {
      reviseProposal.mutate(
        { proposalId: proposal.id, feedback: `Use "${altName}" as the target variable instead.` },
        {
          onSuccess: () => {
            toast.success(`Requested "${altName}" as the new target`);
            queryClient.invalidateQueries({ queryKey: ["proposals", "pending", sessionId] });
            queryClient.invalidateQueries({ queryKey: ["target", sessionId] });
          },
          onError: () => toast.error("Failed to request alternative target"),
        },
      );
    } else {
      try {
        await api.post(`/sessions/${sessionId}/feedback`, {
          message: `Use "${altName}" as the target variable instead.`,
          step: "target_id",
        });
        toast.success(`Suggested "${altName}" as the target`);
      } catch {
        toast.error("Failed to submit suggestion");
      }
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Target Variable</h2>
        <p className="text-muted-foreground">
          Review the AI-identified target variable.
        </p>
      </div>

      <PendingProposals sessionId={sessionId} step="target_id" />

      <StepStatusBanner state={targetState} stepLabel="Target Identification" />

      {config && (
        <>
          <Card>
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-primary/10 p-2">
                  <Target className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <CardTitle className="text-base">
                    Target: {config.target_variable}
                  </CardTitle>
                  <CardDescription>
                    This variable will be predicted by the models.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
          </Card>

          {/* AI Explanation */}
          {aiExplanation && (
            <Card className="border-primary/20 bg-primary/5">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Brain className="h-4 w-4 text-primary" />
                  Why This Target?
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {aiExplanation}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Alternative Targets */}
          {alternatives.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <CircleDot className="h-4 w-4" />
                  Alternative Targets Considered
                </CardTitle>
                <CardDescription>
                  These variables were evaluated but not selected as the primary
                  target. Click &quot;Use This Instead&quot; to switch.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {alternatives.map((alt) => (
                    <div
                      key={alt.name}
                      className="flex items-center gap-3 rounded-md border px-3 py-2"
                    >
                      <Badge variant="secondary" className="shrink-0">
                        {alt.name}
                      </Badge>
                      <p className="flex-1 text-xs text-muted-foreground">
                        {alt.reason}
                      </p>
                      <Button
                        variant="outline"
                        size="sm"
                        className="shrink-0 gap-1 text-xs"
                        onClick={() => handleSuggestAlternative(alt.name)}
                        disabled={reviseProposal.isPending}
                      >
                        <Sparkles className="h-3 w-3" />
                        Use This Instead
                      </Button>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {config.preview.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Data Preview</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b text-xs text-muted-foreground">
                        {Object.keys(config.preview[0]).map((key) => (
                          <th key={key} className="px-2 py-1.5">
                            {key}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {config.preview.slice(0, 5).map((row, i) => (
                        <tr key={i} className="border-b">
                          {Object.values(row).map((val, j) => (
                            <td key={j} className="px-2 py-1.5 text-xs">
                              {String(val)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Revision Controls */}
          <Card>
            <CardContent className="py-4 space-y-3">
              <div className="flex items-center gap-3">
                <Button
                  className="gap-2"
                  size="lg"
                  onClick={handleConfirm}
                  disabled={isPending || isRunning || approveProposal.isPending}
                >
                  {isPending || approveProposal.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <ArrowRight className="h-4 w-4" />
                  )}
                  {hasPendingProposals
                    ? "Approve & Continue"
                    : "Confirm Target & Continue"}
                </Button>
                <Button
                  variant="outline"
                  className="gap-2"
                  onClick={() => setShowRevisionInput(!showRevisionInput)}
                >
                  <MessageSquare className="h-4 w-4" />
                  Suggest a Different Target
                </Button>
              </div>
              {showRevisionInput && (
                <div className="space-y-2">
                  <Textarea
                    placeholder="Describe the target variable you'd like to use, or explain why the current one isn't right..."
                    value={revisionText}
                    onChange={(e) => setRevisionText(e.target.value)}
                    rows={3}
                  />
                  <Button
                    onClick={handleRequestRevision}
                    disabled={!revisionText.trim() || reviseProposal.isPending}
                    className="gap-2"
                  >
                    {reviseProposal.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Sparkles className="h-4 w-4" />
                    )}
                    Submit Revision
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
