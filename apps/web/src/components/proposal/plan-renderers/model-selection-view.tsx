"use client";

import { Badge } from "@/components/ui/badge";
import { Brain, Settings } from "lucide-react";

interface ModelSelectionViewProps {
  plan: Record<string, unknown>;
}

const MODEL_LABELS: Record<string, string> = {
  logistic_regression: "Logistic Regression",
  random_forest: "Random Forest",
  gradient_boosting: "Gradient Boosting",
  svm: "SVM",
  extra_trees: "Extra Trees",
  knn: "K-Nearest Neighbors",
};

export function ModelSelectionView({ plan }: ModelSelectionViewProps) {
  const modelTypes = (plan.model_types ?? []) as string[];
  const tuneHyperparams = plan.tune_hyperparams as boolean | undefined;
  const splitStrategy = plan.split_strategy as string | undefined;
  const dataChars = plan.data_characteristics as Record<string, unknown> | undefined;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Brain className="h-4 w-4 text-purple-500" />
        <span className="text-sm font-medium">Models:</span>
        {modelTypes.map((m) => (
          <Badge key={m} variant="secondary">
            {MODEL_LABELS[m] ?? m}
          </Badge>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <div className="flex items-center gap-1">
          <Settings className="h-3 w-3" />
          <span>Tuning: {tuneHyperparams !== false ? "enabled" : "disabled"}</span>
        </div>
        {splitStrategy && (
          <span>Split: {splitStrategy}</span>
        )}
      </div>

      {dataChars && (
        <div className="text-xs text-muted-foreground rounded-md bg-muted/50 p-2">
          <span className="font-medium">Data: </span>
          {dataChars.row_count as number | undefined} rows,{" "}
          {dataChars.feature_count as number | undefined} features ({dataChars.feature_types as string}),{" "}
          balance: {dataChars.class_balance as string}
        </div>
      )}
    </div>
  );
}
