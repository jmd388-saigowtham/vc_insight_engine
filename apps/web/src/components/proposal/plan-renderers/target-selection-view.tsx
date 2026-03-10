"use client";

import { Badge } from "@/components/ui/badge";
import { Target, Lightbulb } from "lucide-react";

interface TargetSelectionViewProps {
  plan: Record<string, unknown>;
}

export function TargetSelectionView({ plan }: TargetSelectionViewProps) {
  const targetColumn = plan.target_column as string | undefined;
  const method = plan.method as string | undefined;
  const alternatives = plan.alternatives as string[] | undefined;
  const needsDerivation = plan.needs_derivation as boolean | undefined;
  const derivationDescription = plan.derivation_description as string | undefined;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Target className="h-4 w-4 text-purple-500" />
        <span className="text-sm font-medium">Target column:</span>
        <Badge className="bg-purple-600">{targetColumn ?? "Unknown"}</Badge>
        {method && (
          <Badge variant="outline" className="text-[10px]">
            {method}
          </Badge>
        )}
      </div>

      {needsDerivation && derivationDescription && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs dark:border-amber-800 dark:bg-amber-950/30">
          <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
          <div>
            <p className="font-medium text-foreground">Derivation required</p>
            <p className="mt-0.5 text-muted-foreground">{derivationDescription}</p>
          </div>
        </div>
      )}

      {alternatives && alternatives.length > 0 && (
        <div className="text-xs text-muted-foreground">
          <span className="font-medium">Alternatives: </span>
          {alternatives.map((alt) => (
            <Badge key={alt} variant="outline" className="mr-1 text-[10px]">
              {alt}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
