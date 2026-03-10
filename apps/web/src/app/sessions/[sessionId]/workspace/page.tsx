"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useWizardNavigation } from "@/hooks/use-wizard-navigation";
import { useSession } from "@/hooks/use-session";
import { useDatasets } from "@/hooks/use-artifacts";
import { useStepStates } from "@/hooks/use-step-states";
import { useTraceStore } from "@/stores/trace-store";
import { usePendingProposals, useApproveProposal } from "@/hooks/use-proposals";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { StepStatusBanner } from "@/components/step-status-banner";
import {
  TrendingDown,
  TrendingUp,
  RefreshCw,
  ShoppingCart,
  Loader2,
  Database,
  ArrowRight as ArrowRightIcon,
  Brain,
  Play,
} from "lucide-react";
import { toast } from "sonner";
import { PendingProposals } from "@/components/proposal/pending-proposals";

interface Opportunity {
  id: string;
  title: string;
  description: string;
  type: "churn" | "expansion" | "cross_sell" | "upsell";
  confidence: number;
  key_metrics: string[];
}

const TYPE_CONFIG = {
  churn: {
    icon: TrendingDown,
    color: "text-red-500",
    bg: "bg-red-500/10",
  },
  expansion: {
    icon: TrendingUp,
    color: "text-green-500",
    bg: "bg-green-500/10",
  },
  cross_sell: {
    icon: ShoppingCart,
    color: "text-blue-500",
    bg: "bg-blue-500/10",
  },
  upsell: {
    icon: RefreshCw,
    color: "text-purple-500",
    bg: "bg-purple-500/10",
  },
};

export default function WorkspacePage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const { navigateToNext, isPending } = useWizardNavigation("workspace");
  const { data: session } = useSession(sessionId);
  const { data: datasets } = useDatasets(sessionId);
  const { data: stepStates } = useStepStates(sessionId);
  const { data: pendingProposals } = usePendingProposals(sessionId, "opportunity_analysis");
  const approveProposal = useApproveProposal();
  const events = useTraceStore((s) => s.events);
  const queryClient = useQueryClient();
  const [isStarting, setIsStarting] = useState(false);

  const opportunityState = stepStates?.opportunity_analysis ?? stepStates?.data_understanding;
  const STEP_ORDER = ["profiling", "merge_planning", "dtype_handling", "data_understanding", "opportunity_analysis", "target_id", "feature_selection", "eda", "preprocessing", "hypothesis", "feature_eng", "modeling", "threshold_calibration", "explainability", "recommendation", "report"];
  const analysisHasStarted = session?.current_step && STEP_ORDER.indexOf(session.current_step) > STEP_ORDER.indexOf("workspace");

  async function handleStartAnalysis() {
    setIsStarting(true);
    try {
      await api.post(`/sessions/${sessionId}/start-analysis`);
      toast.success("Analysis started! The AI agent is now processing your data.");
    } catch {
      toast.error("Failed to start analysis. Please try again.");
    } finally {
      setIsStarting(false);
    }
  }

  // Extract AI reasoning events for the analysis plan summary
  const reasoningEvents = events.filter(
    (e) =>
      e.event_type === "AI_REASONING" ||
      e.event_type === "PLAN" ||
      e.event_type === "DECISION",
  );
  const planSteps = reasoningEvents
    .map((e) => {
      const payload = e.payload as Record<string, unknown>;
      const candidates = [payload.plan, payload.reasoning, payload.message, payload.decision];
      const val = candidates.find((c) => c != null);
      return typeof val === "string" ? val : null;
    })
    .filter(Boolean) as string[];

  const { data: opportunities, isLoading } = useQuery({
    queryKey: ["opportunities", sessionId],
    queryFn: () =>
      api.get<Opportunity[]>(`/sessions/${sessionId}/opportunities`),
    refetchInterval: opportunityState === "RUNNING" ? 5000 : false,
  });

  async function handleSelect(opportunity: Opportunity) {
    // Prefer proposal approval when a pending proposal exists
    const proposal = pendingProposals?.[0];
    if (proposal) {
      approveProposal.mutate(proposal.id, {
        onSuccess: async () => {
          // Resume pipeline after approval
          try {
            await api.post(`/sessions/${sessionId}/resume`, {
              proposal_id: proposal.id,
              proposal_type: "business",
            });
          } catch {
            // Pipeline resume is best-effort
          }
          queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
          queryClient.invalidateQueries({ queryKey: ["proposals", "pending", sessionId] });
          toast.success(`Selected: ${opportunity.title} — proceeding with analysis`);
          navigateToNext("target");
        },
        onError: () => toast.error("Failed to approve opportunity selection"),
      });
      return;
    }
    // Fallback: submit feedback when no proposal exists
    try {
      await api.post(`/sessions/${sessionId}/feedback`, {
        message: `User selected value creation opportunity: ${opportunity.title} (${opportunity.type}). Focus the analysis on this objective.`,
        step: "opportunity_analysis",
      });
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      toast.success(`Selected: ${opportunity.title} — analysis objective updated`);
      navigateToNext("target");
    } catch {
      toast.error("Failed to persist opportunity selection");
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <Skeleton className="mb-2 h-8 w-48" />
          <Skeleton className="h-4 w-96" />
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="rounded-lg border p-6 space-y-4">
              <div className="flex items-center gap-2">
                <Skeleton className="h-9 w-9 rounded-lg" />
                <div className="space-y-1.5">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-5 w-16 rounded-full" />
                </div>
              </div>
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <div className="space-y-1">
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-1.5 w-full rounded-full" />
              </div>
              <div className="flex gap-1">
                <Skeleton className="h-5 w-16 rounded-full" />
                <Skeleton className="h-5 w-20 rounded-full" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">AI Workspace</h2>
        <p className="text-muted-foreground">
          Based on your data, the AI has identified these value creation
          opportunities. Select one to begin the analysis.
        </p>
      </div>

      <PendingProposals sessionId={sessionId} />

      <StepStatusBanner state={opportunityState} stepLabel="Opportunity Analysis" />

      {/* AI Analysis Plan Summary */}
      {planSteps.length > 0 && (
        <Card className="border-primary/20 bg-primary/5">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Brain className="h-4 w-4 text-primary" />
              AI Analysis Plan
            </CardTitle>
            <CardDescription>
              The orchestrator has outlined the following analysis strategy.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {planSteps.map((step, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm">
                  <Badge
                    variant="outline"
                    className="mt-0.5 shrink-0 text-[10px] h-5 w-5 items-center justify-center p-0"
                  >
                    {idx + 1}
                  </Badge>
                  <span className="text-muted-foreground">{step}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {(opportunities ?? []).map((opp) => {
          const config = TYPE_CONFIG[opp.type] ?? {
            icon: TrendingUp,
            color: "text-gray-500",
            bg: "bg-gray-500/10",
          };
          const Icon = config.icon;

          return (
            <Card
              key={opp.id}
              className="cursor-pointer transition-all hover:shadow-md hover:ring-1 hover:ring-primary/20"
              onClick={() => handleSelect(opp)}
            >
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <div className={`rounded-lg p-2 ${config.bg}`}>
                    <Icon className={`h-5 w-5 ${config.color}`} />
                  </div>
                  <div>
                    <CardTitle className="text-base">{opp.title}</CardTitle>
                    <Badge variant="outline" className="mt-1 text-xs">
                      {opp.type.replace("_", " ")}
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <CardDescription>{opp.description}</CardDescription>

                <div className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Confidence</span>
                    <span className="font-medium">
                      {(opp.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <Progress value={opp.confidence * 100} className="h-1.5" />
                </div>

                <div className="flex flex-wrap gap-1">
                  {opp.key_metrics.map((metric) => (
                    <Badge
                      key={metric}
                      variant="secondary"
                      className="text-xs"
                    >
                      {metric}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {(!opportunities || opportunities.length === 0) && (
        <Card className="p-12 text-center">
          {analysisHasStarted ? (
            <>
              <Loader2 className="mx-auto mb-4 h-8 w-8 animate-spin text-primary" />
              <p className="text-muted-foreground">
                AI is analyzing your data... Check the live trace for progress.
              </p>
            </>
          ) : (
            <>
              <Play className="mx-auto mb-4 h-8 w-8 text-primary" />
              <h3 className="mb-2 text-lg font-semibold">Ready to Analyze</h3>
              <p className="mb-6 text-muted-foreground">
                Your data has been uploaded and profiled. Start the AI-driven
                analysis to identify value creation opportunities.
              </p>
              <Button
                size="lg"
                onClick={handleStartAnalysis}
                disabled={isStarting}
              >
                {isStarting ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Play className="mr-2 h-4 w-4" />
                )}
                Start Analysis
              </Button>
            </>
          )}
        </Card>
      )}

      {/* Dataset Lineage */}
      {datasets && datasets.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Database className="h-4 w-4" />
              Dataset Lineage
            </CardTitle>
            <CardDescription>
              Data transformations tracked across the pipeline.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-2">
              {datasets.map((ds, idx) => (
                <div key={ds.id} className="flex items-center gap-2">
                  {idx > 0 && (
                    <ArrowRightIcon className="h-3 w-3 text-muted-foreground" />
                  )}
                  <div className="rounded-md border px-3 py-1.5">
                    <p className="text-xs font-medium">{ds.name}</p>
                    <div className="flex gap-2 mt-0.5">
                      <Badge variant="outline" className="text-[10px] h-4">
                        {ds.source_type}
                      </Badge>
                      {ds.row_count != null && (
                        <span className="text-[10px] text-muted-foreground">
                          {ds.row_count.toLocaleString()} rows
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
