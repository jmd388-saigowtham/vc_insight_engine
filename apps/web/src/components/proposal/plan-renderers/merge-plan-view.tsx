"use client";

import { Badge } from "@/components/ui/badge";
import { GitMerge, ArrowRight, AlertTriangle } from "lucide-react";

interface MergePlanViewProps {
  plan: Record<string, unknown>;
}

export function MergePlanView({ plan }: MergePlanViewProps) {
  const steps = (plan.merge_steps ?? plan.steps ?? []) as Array<{
    left_file?: string;
    right_file?: string;
    join_key?: string;
    join_keys?: string[];
    join_type?: string;
    confidence?: number;
  }>;
  const alternatives = plan.alternatives as string[] | undefined;

  if (steps.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {plan.summary as string || "No merge steps defined."}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {steps.map((step, i) => {
        const keys = step.join_keys ?? (step.join_key ? [step.join_key] : []);
        return (
          <div
            key={i}
            className="flex items-center gap-2 rounded-md border p-2 text-sm"
          >
            <GitMerge className="h-4 w-4 shrink-0 text-blue-500" />
            <span className="font-medium">{step.left_file}</span>
            <ArrowRight className="h-3 w-3 text-muted-foreground" />
            <span className="font-medium">{step.right_file}</span>
            <Badge variant="outline" className="ml-auto text-[10px]">
              {step.join_type ?? "inner"}
            </Badge>
            {keys.map((k) => (
              <Badge key={k} variant="secondary" className="text-[10px]">
                {k}
              </Badge>
            ))}
            {step.confidence !== undefined && (
              <span className="text-[10px] text-muted-foreground">
                {Math.round(step.confidence * 100)}%
              </span>
            )}
          </div>
        );
      })}
      {alternatives && alternatives.length > 0 && (
        <div className="flex items-start gap-2 text-xs text-muted-foreground">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-500" />
          <span>Alternatives: {alternatives.join(", ")}</span>
        </div>
      )}
    </div>
  );
}
