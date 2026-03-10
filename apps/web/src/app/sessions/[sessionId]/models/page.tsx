"use client";

import { useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useWizardNavigation } from "@/hooks/use-wizard-navigation";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import {
  ArrowRight,
  ChevronDown,
  Trophy,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  TrendingDown,
  Crosshair,
  Plus,
  Sparkles,
  SlidersHorizontal,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import type { ModelResult, ThresholdInfo } from "@/types/api";
import { PendingProposals } from "@/components/proposal/pending-proposals";
import { useStepStates } from "@/hooks/use-step-states";
import { usePendingProposals } from "@/hooks/use-proposals";
import { StepStatusBanner } from "@/components/step-status-banner";

const ADDITIONAL_MODEL_TYPES = [
  { value: "extra_trees", label: "Extra Trees" },
  { value: "knn", label: "K-Nearest Neighbors" },
  { value: "xgboost", label: "XGBoost" },
  { value: "lightgbm", label: "LightGBM" },
];

export default function ModelsPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const queryClient = useQueryClient();
  const { navigateToNext, isPending } = useWizardNavigation("models");
  const { data: stepStates } = useStepStates(sessionId);
  const modelingState = stepStates?.modeling ?? "NOT_STARTED";
  const { data: pendingProposals } = usePendingProposals(sessionId, "modeling");
  const hasPendingProposals = (pendingProposals?.length ?? 0) > 0;

  const [selectedForShap, setSelectedForShap] = useState<string | null>(null);
  const [trainDialogOpen, setTrainDialogOpen] = useState(false);
  const [newModelType, setNewModelType] = useState("");

  const { data: models, isLoading } = useQuery({
    queryKey: ["models", sessionId],
    queryFn: () =>
      api.get<ModelResult[]>(`/sessions/${sessionId}/models`),
  });

  const selectModelMutation = useMutation({
    mutationFn: (modelName: string) =>
      api.post(`/sessions/${sessionId}/select-model`, {
        model_name: modelName,
      }),
    onSuccess: (_, modelName) => {
      toast.success(`Selected "${modelName}" for SHAP analysis`);
      queryClient.invalidateQueries({ queryKey: ["models", sessionId] });
    },
    onError: () => {
      toast.error("Failed to select model");
    },
  });

  const trainModelMutation = useMutation({
    mutationFn: (modelType: string) =>
      api.post(`/sessions/${sessionId}/feedback`, {
        message: `Please train an additional ${modelType} model.`,
        step: "modeling",
      }),
    onSuccess: () => {
      toast.success("Model training requested — the AI will propose a plan");
      setTrainDialogOpen(false);
      setNewModelType("");
      queryClient.invalidateQueries({ queryKey: ["proposals", "pending", sessionId] });
    },
    onError: () => {
      toast.error("Failed to request model training");
    },
  });

  const sortedModels = [...(models ?? [])].sort(
    (a, b) => b.f1_score - a.f1_score,
  );

  const hasLeakageWarning = sortedModels.some(
    (m) => m.train_metrics && m.diagnostics?.status === "overfitting",
  );

  function handleSelectForShap(modelName: string) {
    setSelectedForShap(modelName);
    selectModelMutation.mutate(modelName);
  }

  function handleContinue() {
    navigateToNext("shap");
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <Skeleton className="mb-2 h-8 w-48" />
          <Skeleton className="h-4 w-72" />
        </div>
        <div className="rounded-lg border">
          <div className="border-b px-4 py-3 flex gap-8">
            {["#", "Model", "Accuracy", "Precision", "Recall", "F1", "AUC-ROC", "Fit"].map((col) => (
              <Skeleton key={col} className="h-3 w-16" />
            ))}
          </div>
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="flex items-center gap-8 border-b px-4 py-3">
              <Skeleton className="h-4 w-4 rounded-full" />
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-3 w-12" />
              <Skeleton className="h-3 w-12" />
              <Skeleton className="h-3 w-12" />
              <Skeleton className="h-3 w-12" />
              <Skeleton className="h-3 w-12" />
              <Skeleton className="h-3 w-16" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Model Leaderboard</h2>
        <p className="text-muted-foreground">
          Models ranked by F1 score. The best model is highlighted.
        </p>
      </div>

      <PendingProposals sessionId={sessionId} step="modeling" />
      <StepStatusBanner state={modelingState} stepLabel="Model Training" />

      {hasLeakageWarning && (
        <Card className="border-amber-500/50 bg-amber-500/5">
          <CardContent className="flex items-start gap-3 p-4">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
            <div>
              <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
                Potential Overfitting Detected
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                One or more models show a significant gap between training and test
                performance. Review the diagnostics in the expanded row for details.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b text-xs font-medium text-muted-foreground">
                  <th className="px-4 py-3 w-8">#</th>
                  <th className="px-4 py-3">Model</th>
                  <th className="px-4 py-3 text-right">Accuracy</th>
                  <th className="px-4 py-3 text-right">Precision</th>
                  <th className="px-4 py-3 text-right">Recall</th>
                  <th className="px-4 py-3 text-right">F1</th>
                  <th className="px-4 py-3 text-right">AUC-ROC</th>
                  <th className="px-4 py-3 text-center">Fit</th>
                  <th className="px-4 py-3 text-center">SHAP</th>
                  <th className="px-4 py-3 w-10"></th>
                </tr>
              </thead>
              <tbody>
                {sortedModels.map((model, idx) => (
                  <ModelRow
                    key={model.id}
                    model={model}
                    rank={idx + 1}
                    sessionId={sessionId}
                    selectedForShap={selectedForShap}
                    onSelectForShap={handleSelectForShap}
                    selectPending={selectModelMutation.isPending}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {sortedModels.length === 0 && (
        <Card className="p-12 text-center">
          <Loader2 className="mx-auto mb-4 h-8 w-8 animate-spin text-primary" />
          <p className="text-muted-foreground">
            Training models... Check the live trace for progress.
          </p>
        </Card>
      )}

      {sortedModels.length > 0 && (
        <div className="flex items-center gap-3">
          <Dialog open={trainDialogOpen} onOpenChange={setTrainDialogOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" className="gap-2">
                <Plus className="h-4 w-4" />
                Train Additional Model
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Train Additional Model</DialogTitle>
                <DialogDescription>
                  Select a model type to train on the same dataset. Results will
                  be added to the leaderboard.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-3 py-2">
                <div className="space-y-2">
                  <Label htmlFor="model-type">Model Type</Label>
                  <Select value={newModelType} onValueChange={setNewModelType}>
                    <SelectTrigger id="model-type">
                      <SelectValue placeholder="Select a model type..." />
                    </SelectTrigger>
                    <SelectContent>
                      {ADDITIONAL_MODEL_TYPES.map((mt) => (
                        <SelectItem key={mt.value} value={mt.value}>
                          {mt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <DialogFooter>
                <Button
                  onClick={() => trainModelMutation.mutate(newModelType)}
                  disabled={!newModelType || trainModelMutation.isPending}
                  className="gap-2"
                >
                  {trainModelMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4" />
                  )}
                  {trainModelMutation.isPending ? "Training..." : "Start Training"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <Button
            className="gap-2"
            size="lg"
            onClick={handleContinue}
            disabled={isPending || modelingState === "RUNNING" || hasPendingProposals}
          >
            {isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ArrowRight className="h-4 w-4" />
            )}
            Continue to SHAP Analysis
          </Button>
        </div>
      )}
    </div>
  );
}

function DiagnosticsBadge({ status }: { status: string }) {
  if (status === "good_fit") {
    return (
      <Badge variant="outline" className="gap-1 border-green-500/50 text-green-600 dark:text-green-400">
        <CheckCircle2 className="h-3 w-3" />
        Good
      </Badge>
    );
  }
  if (status === "overfitting") {
    return (
      <Badge variant="outline" className="gap-1 border-amber-500/50 text-amber-600 dark:text-amber-400">
        <AlertTriangle className="h-3 w-3" />
        Overfit
      </Badge>
    );
  }
  if (status === "underfitting") {
    return (
      <Badge variant="outline" className="gap-1 border-red-500/50 text-red-600 dark:text-red-400">
        <TrendingDown className="h-3 w-3" />
        Underfit
      </Badge>
    );
  }
  return null;
}

function MetricCell({ value, label }: { value: number; label?: string }) {
  return (
    <span className="font-mono text-xs" title={label}>
      {(value * 100).toFixed(1)}%
    </span>
  );
}

function ModelRow({
  model,
  rank,
  sessionId,
  selectedForShap,
  onSelectForShap,
  selectPending,
}: {
  model: ModelResult;
  rank: number;
  sessionId: string;
  selectedForShap: string | null;
  onSelectForShap: (name: string) => void;
  selectPending: boolean;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [sliderValue, setSliderValue] = useState(
    model.threshold_info?.threshold ?? 0.5,
  );
  const [thresholdMetrics, setThresholdMetrics] = useState<ThresholdInfo | null>(
    null,
  );
  const hasDiag = !!model.diagnostics;
  const hasTrain = !!model.train_metrics;
  const isSelectedForShap = selectedForShap === model.model_name;

  const retrainMutation = useMutation({
    mutationFn: (threshold: number) =>
      api.post(`/sessions/${sessionId}/feedback`, {
        message: `Re-evaluate model "${model.model_name}" at threshold ${threshold}.`,
        step: "threshold_calibration",
      }),
    onSuccess: () => {
      toast.success("Threshold evaluation requested");
      queryClient.invalidateQueries({ queryKey: ["proposals", "pending", sessionId] });
    },
    onError: () => {
      toast.error("Failed to request threshold re-evaluation");
    },
  });

  const handleThresholdCommit = useCallback(
    (value: number) => {
      if (value > 0 && value < 1) {
        retrainMutation.mutate(value);
      }
    },
    [retrainMutation],
  );

  return (
    <>
      <tr
        className={cn(
          "cursor-pointer border-b hover:bg-muted/50",
          model.is_best && "bg-primary/5",
        )}
        onClick={() => setOpen((o) => !o)}
      >
        <td className="px-4 py-3">
          {model.is_best ? (
            <Trophy className="h-4 w-4 text-amber-500" />
          ) : (
            <span className="text-muted-foreground">{rank}</span>
          )}
        </td>
        <td className="px-4 py-3 font-medium">
          {model.model_name}
          {model.is_best && (
            <Badge className="ml-2 text-xs" variant="default">
              Best
            </Badge>
          )}
          {isSelectedForShap && (
            <Badge className="ml-2 text-xs" variant="outline">
              <Sparkles className="mr-1 h-3 w-3" />
              SHAP Target
            </Badge>
          )}
        </td>
        <td className="px-4 py-3 text-right font-mono text-xs">
          {(model.accuracy * 100).toFixed(1)}%
        </td>
        <td className="px-4 py-3 text-right font-mono text-xs">
          {(model.precision * 100).toFixed(1)}%
        </td>
        <td className="px-4 py-3 text-right font-mono text-xs">
          {(model.recall * 100).toFixed(1)}%
        </td>
        <td className="px-4 py-3 text-right font-mono text-xs font-semibold">
          {(model.f1_score * 100).toFixed(1)}%
        </td>
        <td className="px-4 py-3 text-right font-mono text-xs">
          {(model.auc_roc * 100).toFixed(1)}%
        </td>
        <td className="px-4 py-3 text-center">
          {hasDiag && <DiagnosticsBadge status={model.diagnostics!.status} />}
        </td>
        <td className="px-4 py-3 text-center">
          <input
            type="radio"
            name="shap-model"
            checked={isSelectedForShap}
            disabled={selectPending}
            onChange={(e) => {
              e.stopPropagation();
              onSelectForShap(model.model_name);
            }}
            onClick={(e) => e.stopPropagation()}
            className="h-4 w-4 cursor-pointer accent-primary"
          />
        </td>
        <td className="px-4 py-3">
          <ChevronDown
            className={cn(
              "h-4 w-4 text-muted-foreground transition-transform",
              open && "rotate-180",
            )}
          />
        </td>
      </tr>
      {open && (
        <tr className="border-b bg-muted/30">
          <td colSpan={10} className="px-4 py-4">
            <div className="space-y-4">
              {/* Train vs Test metrics comparison */}
              {hasTrain && (
                <div>
                  <p className="mb-2 text-xs font-medium">
                    Train vs Test Metrics
                  </p>
                  <div className="overflow-x-auto">
                    <table className="text-xs">
                      <thead>
                        <tr className="text-muted-foreground">
                          <th className="pr-6 py-1 text-left font-medium">Split</th>
                          <th className="pr-6 py-1 text-right font-medium">Accuracy</th>
                          <th className="pr-6 py-1 text-right font-medium">Precision</th>
                          <th className="pr-6 py-1 text-right font-medium">Recall</th>
                          <th className="pr-6 py-1 text-right font-medium">F1</th>
                          <th className="pr-6 py-1 text-right font-medium">AUC-ROC</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td className="pr-6 py-1 font-medium">Train</td>
                          <td className="pr-6 py-1 text-right font-mono">
                            <MetricCell value={model.train_metrics!.accuracy} />
                          </td>
                          <td className="pr-6 py-1 text-right font-mono">
                            <MetricCell value={model.train_metrics!.precision} />
                          </td>
                          <td className="pr-6 py-1 text-right font-mono">
                            <MetricCell value={model.train_metrics!.recall} />
                          </td>
                          <td className="pr-6 py-1 text-right font-mono">
                            <MetricCell value={model.train_metrics!.f1} />
                          </td>
                          <td className="pr-6 py-1 text-right font-mono">
                            <MetricCell value={model.train_metrics!.roc_auc} />
                          </td>
                        </tr>
                        {model.val_metrics && (
                          <tr>
                            <td className="pr-6 py-1 font-medium">Validation</td>
                            <td className="pr-6 py-1 text-right font-mono">
                              <MetricCell value={model.val_metrics.accuracy} />
                            </td>
                            <td className="pr-6 py-1 text-right font-mono">
                              <MetricCell value={model.val_metrics.precision} />
                            </td>
                            <td className="pr-6 py-1 text-right font-mono">
                              <MetricCell value={model.val_metrics.recall} />
                            </td>
                            <td className="pr-6 py-1 text-right font-mono">
                              <MetricCell value={model.val_metrics.f1} />
                            </td>
                            <td className="pr-6 py-1 text-right font-mono">
                              <MetricCell value={model.val_metrics.roc_auc} />
                            </td>
                          </tr>
                        )}
                        <tr className="font-semibold">
                          <td className="pr-6 py-1 font-medium">Test</td>
                          <td className="pr-6 py-1 text-right font-mono">
                            <MetricCell value={model.accuracy} />
                          </td>
                          <td className="pr-6 py-1 text-right font-mono">
                            <MetricCell value={model.precision} />
                          </td>
                          <td className="pr-6 py-1 text-right font-mono">
                            <MetricCell value={model.recall} />
                          </td>
                          <td className="pr-6 py-1 text-right font-mono">
                            <MetricCell value={model.f1_score} />
                          </td>
                          <td className="pr-6 py-1 text-right font-mono">
                            <MetricCell value={model.auc_roc} />
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Diagnostics message */}
              {hasDiag && model.diagnostics!.message && (
                <div className={cn(
                  "rounded-md px-3 py-2 text-xs",
                  model.diagnostics!.status === "good_fit" && "bg-green-500/10 text-green-700 dark:text-green-400",
                  model.diagnostics!.status === "overfitting" && "bg-amber-500/10 text-amber-700 dark:text-amber-400",
                  model.diagnostics!.status === "underfitting" && "bg-red-500/10 text-red-700 dark:text-red-400",
                )}>
                  {model.diagnostics!.message}
                </div>
              )}

              {/* Classification Threshold Slider */}
              {(() => {
                const info = thresholdMetrics ?? model.threshold_info ?? model.diagnostics?.threshold_info;
                return (
                  <div>
                    <p className="mb-2 text-xs font-medium flex items-center gap-1.5">
                      <SlidersHorizontal className="h-3.5 w-3.5" />
                      Classification Threshold
                    </p>
                    <div className="space-y-3 rounded-md bg-muted/50 px-3 py-3">
                      <div className="flex items-center gap-3">
                        <span className="text-[10px] text-muted-foreground w-6">0</span>
                        <input
                          type="range"
                          min={0.01}
                          max={0.99}
                          step={0.01}
                          value={sliderValue}
                          onChange={(e) => setSliderValue(parseFloat(e.target.value))}
                          onMouseUp={() => handleThresholdCommit(sliderValue)}
                          onTouchEnd={() => handleThresholdCommit(sliderValue)}
                          onClick={(e) => e.stopPropagation()}
                          className="flex-1 h-2 cursor-pointer accent-primary"
                        />
                        <span className="text-[10px] text-muted-foreground w-6">1</span>
                        <span className="text-sm font-bold font-mono w-14 text-right">
                          {sliderValue.toFixed(2)}
                        </span>
                        {retrainMutation.isPending && (
                          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                        )}
                      </div>
                      {info && info.f1_at_threshold != null && (
                        <div className="flex items-center gap-4">
                          <div className="text-center">
                            <p className="text-sm font-mono">{(info.f1_at_threshold * 100).toFixed(1)}%</p>
                            <p className="text-[10px] text-muted-foreground">F1</p>
                          </div>
                          {info.precision_at_threshold != null && (
                            <div className="text-center">
                              <p className="text-sm font-mono">{(info.precision_at_threshold * 100).toFixed(1)}%</p>
                              <p className="text-[10px] text-muted-foreground">Precision</p>
                            </div>
                          )}
                          {info.recall_at_threshold != null && (
                            <div className="text-center">
                              <p className="text-sm font-mono">{(info.recall_at_threshold * 100).toFixed(1)}%</p>
                              <p className="text-[10px] text-muted-foreground">Recall</p>
                            </div>
                          )}
                          <Badge variant="outline" className="ml-auto text-[10px]">
                            {info.method === "user_specified" ? "User set" : info.method === "default" ? "Default" : "Auto-optimized"}
                          </Badge>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}

              {/* Confusion Matrix */}
              {model.confusion_matrix && (
                <div>
                  <p className="mb-2 text-xs font-medium">Confusion Matrix</p>
                  <div className="inline-grid grid-cols-2 gap-1">
                    {model.confusion_matrix.map((row, i) =>
                      row.map((val, j) => (
                        <div
                          key={`${i}-${j}`}
                          className={cn(
                            "flex h-12 w-16 items-center justify-center rounded text-xs font-mono",
                            i === j
                              ? "bg-green-500/20 text-green-700"
                              : "bg-red-500/10 text-red-600",
                          )}
                        >
                          {val}
                        </div>
                      )),
                    )}
                  </div>
                  <div className="mt-1 flex gap-4 text-[10px] text-muted-foreground">
                    <span>Rows: Actual</span>
                    <span>Cols: Predicted</span>
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
