"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useArtifacts } from "@/hooks/use-artifacts";
import { useWizardNavigation } from "@/hooks/use-wizard-navigation";
import { useRerun } from "@/hooks/use-rerun";
import { useSession } from "@/hooks/use-session";
import { useStepStates } from "@/hooks/use-step-states";
import { usePendingProposals } from "@/hooks/use-proposals";
import { ChartGrid } from "@/components/charts/chart-grid";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { StepStatusBanner } from "@/components/step-status-banner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { ArrowRight, Loader2, RefreshCw, AlertTriangle, Plus, Wand2, Play } from "lucide-react";
import { toast } from "sonner";
import { PendingProposals } from "@/components/proposal/pending-proposals";

export default function EdaPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const queryClient = useQueryClient();
  const { data: stepStates } = useStepStates(sessionId);
  const { data: pendingEdaProposals } = usePendingProposals(sessionId, "eda");
  const { data: session } = useSession(sessionId);
  const edaState = stepStates?.eda;
  const edaIsRunning = edaState === "RUNNING" || session?.step_states?.eda === "RUNNING";
  const { data: artifacts, isLoading } = useArtifacts(sessionId, "eda", {
    refetchInterval: edaIsRunning ? 5000 : false,
  });
  const { navigateToNext, isPending } = useWizardNavigation("eda");
  const rerun = useRerun(sessionId);
  const [isGenerating, setIsGenerating] = useState(false);

  const [customPlotRequest, setCustomPlotRequest] = useState("");

  const customPlotMutation = useMutation({
    mutationFn: (request: string) =>
      api.post(`/sessions/${sessionId}/feedback`, {
        message: `Generate custom EDA plot: ${request}`,
        step: "eda",
      }),
    onSuccess: () => {
      toast.success("Custom plot requested — the AI will generate it");
      setCustomPlotRequest("");
      queryClient.invalidateQueries({
        queryKey: ["artifacts", sessionId, "eda"],
      });
    },
    onError: () => {
      toast.error("Failed to submit plot request. Please try again.");
    },
  });

  const isStale = edaState === "STALE" || session?.step_states?.eda === "STALE";
  const hasPendingProposal = (pendingEdaProposals?.length ?? 0) > 0;

  async function handleGenerateEda() {
    setIsGenerating(true);
    try {
      await api.post(`/sessions/${sessionId}/rerun/eda`);
      toast.success("EDA analysis triggered — the AI will propose an analysis plan");
      queryClient.invalidateQueries({ queryKey: ["proposals", "pending", sessionId, "eda"] });
    } catch {
      toast.error("Failed to trigger EDA analysis");
    } finally {
      setIsGenerating(false);
    }
  }

  function handleContinue() {
    navigateToNext("hypotheses");
  }

  function handleCustomPlotSubmit() {
    if (!customPlotRequest.trim()) return;
    customPlotMutation.mutate(customPlotRequest.trim());
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Exploratory Data Analysis</h2>
        <p className="text-muted-foreground">
          AI-generated visualizations including distributions, correlations, and
          feature importance plots.
        </p>
      </div>

      <PendingProposals sessionId={sessionId} step="eda" />

      <StepStatusBanner state={edaState} stepLabel="Exploratory Data Analysis" />

      {isStale && (
        <div className="flex items-center gap-3 rounded-lg border border-yellow-300 bg-yellow-50 p-4 dark:border-yellow-700 dark:bg-yellow-950">
          <AlertTriangle className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
          <div className="flex-1">
            <p className="text-sm font-medium text-yellow-800 dark:text-yellow-200">
              Results are stale
            </p>
            <p className="text-xs text-yellow-600 dark:text-yellow-400">
              Upstream data has changed. Re-run to update results.
            </p>
          </div>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" size="sm" className="gap-1.5">
                <RefreshCw className="h-3.5 w-3.5" />
                Re-run
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Re-run EDA Analysis?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will re-run EDA and all downstream steps (hypotheses,
                  modeling, SHAP, recommendations, report). Existing results
                  for those steps will be replaced.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => rerun.mutate("eda")}
                  disabled={rerun.isPending}
                >
                  {rerun.isPending ? (
                    <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="mr-1.5 h-4 w-4" />
                  )}
                  Re-run
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}

      <ChartGrid artifacts={artifacts ?? []} loading={isLoading} />

      {(!artifacts || artifacts.length === 0) && !isLoading && (
        <Card className="p-8 text-center">
          {edaState === "RUNNING" || session?.step_states?.eda === "RUNNING" ? (
            <>
              <Loader2 className="mx-auto mb-4 h-8 w-8 animate-spin text-primary" />
              <h3 className="text-lg font-semibold mb-2">Generating EDA Visualizations</h3>
              <p className="text-muted-foreground">
                The AI agent is generating charts and insights. Check the live trace for progress.
              </p>
            </>
          ) : hasPendingProposal ? (
            <>
              <Wand2 className="mx-auto mb-4 h-8 w-8 text-primary" />
              <h3 className="text-lg font-semibold mb-2">EDA Plan Awaiting Approval</h3>
              <p className="text-muted-foreground mb-4">
                Review the pending EDA proposal above and approve it to begin generating visualizations.
              </p>
            </>
          ) : edaState === "READY" ? (
            <>
              <Play className="mx-auto mb-4 h-8 w-8 text-primary" />
              <h3 className="text-lg font-semibold mb-2">Ready to Generate EDA</h3>
              <p className="text-muted-foreground mb-4">
                Start the EDA analysis to generate visualizations. The AI will first propose an analysis plan for your review.
              </p>
              <Button
                size="lg"
                onClick={handleGenerateEda}
                disabled={isGenerating}
                className="gap-2"
              >
                {isGenerating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                Generate EDA
              </Button>
            </>
          ) : (
            <>
              <Wand2 className="mx-auto mb-4 h-8 w-8 text-primary" />
              <h3 className="text-lg font-semibold mb-2">EDA Not Yet Started</h3>
              <p className="text-muted-foreground mb-4">
                The EDA step will generate visualizations when the pipeline reaches this stage.
                Check pending proposals above to approve/revise the EDA plan.
              </p>
            </>
          )}
        </Card>
      )}

      {/* Request Custom Plot */}
      {artifacts && artifacts.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Wand2 className="h-4 w-4" />
              Request Custom Plot
            </CardTitle>
            <CardDescription>
              Describe a custom visualization you would like the AI to generate
              from your data.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              placeholder="e.g., Show a scatter plot of revenue vs. churn rate grouped by industry segment..."
              value={customPlotRequest}
              onChange={(e) => setCustomPlotRequest(e.target.value)}
              rows={3}
              disabled={customPlotMutation.isPending}
            />
            <Button
              onClick={handleCustomPlotSubmit}
              disabled={
                !customPlotRequest.trim() || customPlotMutation.isPending
              }
              className="gap-2"
            >
              {customPlotMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Wand2 className="h-4 w-4" />
              )}
              {customPlotMutation.isPending
                ? "Generating..."
                : "Generate Plot"}
            </Button>
          </CardContent>
        </Card>
      )}

      {artifacts && artifacts.length > 0 && (
        <div className="flex items-center gap-3">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" className="gap-2">
                <Plus className="h-4 w-4" />
                Re-run EDA with New Plots
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Re-run EDA Analysis?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will regenerate EDA visualizations and invalidate downstream
                  steps (hypotheses, modeling, SHAP, recommendations, report).
                  Existing EDA results will be replaced with a fresh set of plots.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => rerun.mutate("eda")}
                  disabled={rerun.isPending}
                >
                  {rerun.isPending ? (
                    <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="mr-1.5 h-4 w-4" />
                  )}
                  Re-run EDA
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <div className="flex flex-col items-start gap-1">
            <Button
              className="gap-2"
              size="lg"
              onClick={handleContinue}
              disabled={isPending || edaIsRunning || hasPendingProposal || !artifacts || artifacts.length === 0}
            >
              {isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowRight className="h-4 w-4" />
              )}
              Continue to Hypotheses
            </Button>
            {edaIsRunning && hasPendingProposal && (
              <p className="text-xs text-muted-foreground">Generating EDA proposal...</p>
            )}
            {edaIsRunning && !hasPendingProposal && (
              <p className="text-xs text-muted-foreground">Executing approved EDA plan...</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
