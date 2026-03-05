"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useUpdateSession } from "@/hooks/use-session";
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
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  ArrowRight,
  ChevronDown,
  Trophy,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ModelResult } from "@/types/api";

export default function ModelsPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;
  const updateSession = useUpdateSession(sessionId);

  const { data: models, isLoading } = useQuery({
    queryKey: ["models", sessionId],
    queryFn: () =>
      api.get<ModelResult[]>(`/sessions/${sessionId}/models`),
  });

  const sortedModels = [...(models ?? [])].sort(
    (a, b) => b.f1_score - a.f1_score,
  );

  function handleContinue() {
    updateSession.mutate(
      { current_step: "shap" },
      {
        onSuccess: () =>
          router.push(`/sessions/${sessionId}/shap`),
      },
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
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
                  <th className="px-4 py-3 w-10"></th>
                </tr>
              </thead>
              <tbody>
                {sortedModels.map((model, idx) => (
                  <ModelRow
                    key={model.id}
                    model={model}
                    rank={idx + 1}
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
        <Button
          className="gap-2"
          size="lg"
          onClick={handleContinue}
          disabled={updateSession.isPending}
        >
          {updateSession.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ArrowRight className="h-4 w-4" />
          )}
          Continue to SHAP Analysis
        </Button>
      )}
    </div>
  );
}

function ModelRow({
  model,
  rank,
}: {
  model: ModelResult;
  rank: number;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Collapsible asChild open={open} onOpenChange={setOpen}>
      <>
        <CollapsibleTrigger asChild>
          <tr
            className={cn(
              "cursor-pointer border-b hover:bg-muted/50",
              model.is_best && "bg-primary/5",
            )}
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
            <td className="px-4 py-3">
              {model.confusion_matrix && (
                <ChevronDown
                  className={cn(
                    "h-4 w-4 text-muted-foreground transition-transform",
                    open && "rotate-180",
                  )}
                />
              )}
            </td>
          </tr>
        </CollapsibleTrigger>
        {model.confusion_matrix && (
          <CollapsibleContent asChild>
            <tr className="border-b bg-muted/30">
              <td colSpan={8} className="px-4 py-4">
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
              </td>
            </tr>
          </CollapsibleContent>
        )}
      </>
    </Collapsible>
  );
}
