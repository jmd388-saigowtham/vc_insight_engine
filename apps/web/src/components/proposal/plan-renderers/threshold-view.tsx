"use client";

import { Badge } from "@/components/ui/badge";
import { Gauge, TrendingUp, TrendingDown } from "lucide-react";

interface ThresholdViewProps {
  plan: Record<string, unknown>;
}

export function ThresholdView({ plan }: ThresholdViewProps) {
  const threshold = plan.recommended_threshold as number | undefined;
  const method = plan.method as string | undefined;
  const precision = plan.precision_at_threshold as number | undefined;
  const recall = plan.recall_at_threshold as number | undefined;
  const f1 = plan.f1_at_threshold as number | undefined;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Gauge className="h-4 w-4 text-teal-500" />
        <span className="text-sm font-medium">Recommended threshold:</span>
        <Badge className="bg-teal-600 text-lg px-3">
          {threshold !== undefined ? threshold.toFixed(3) : "N/A"}
        </Badge>
        {method && (
          <Badge variant="outline" className="text-[10px]">{method}</Badge>
        )}
      </div>

      {(precision !== undefined || recall !== undefined || f1 !== undefined) && (
        <div className="flex gap-4 text-xs text-muted-foreground">
          {precision !== undefined && (
            <div className="flex items-center gap-1">
              <TrendingUp className="h-3 w-3 text-green-500" />
              Precision: {(precision * 100).toFixed(1)}%
            </div>
          )}
          {recall !== undefined && (
            <div className="flex items-center gap-1">
              <TrendingDown className="h-3 w-3 text-blue-500" />
              Recall: {(recall * 100).toFixed(1)}%
            </div>
          )}
          {f1 !== undefined && (
            <div>F1: {(f1 * 100).toFixed(1)}%</div>
          )}
        </div>
      )}
    </div>
  );
}
