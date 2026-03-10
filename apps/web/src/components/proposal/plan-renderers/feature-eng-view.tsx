"use client";

import { Badge } from "@/components/ui/badge";
import { Layers, Sigma, Combine } from "lucide-react";

interface FeatureEngViewProps {
  plan: Record<string, unknown>;
}

const METHOD_LABELS: Record<string, string> = {
  standard: "StandardScaler",
  minmax: "MinMaxScaler",
  robust: "RobustScaler",
};

export function FeatureEngView({ plan }: FeatureEngViewProps) {
  const scaling = plan.scaling as Record<string, unknown> | undefined;
  const polynomial = plan.polynomial as Record<string, unknown> | undefined;
  const interactions = plan.interactions as Record<string, unknown> | undefined;

  const polyEnabled = !!(polynomial && polynomial.enabled);
  const interEnabled = !!(interactions && interactions.enabled);

  return (
    <div className="space-y-2">
      {scaling && (
        <div className="flex items-center gap-2 text-sm">
          <Layers className="h-4 w-4 text-blue-500" />
          <span>Scaling:</span>
          <Badge variant="secondary">
            {METHOD_LABELS[String(scaling.method ?? "standard")] ?? String(scaling.method)}
          </Badge>
          {(scaling.columns as string[] | undefined)?.length ? (
            <span className="text-xs text-muted-foreground">
              ({(scaling.columns as string[]).length} columns)
            </span>
          ) : null}
        </div>
      )}

      {polyEnabled && polynomial && (
        <div className="flex items-center gap-2 text-sm">
          <Sigma className="h-4 w-4 text-purple-500" />
          <span>Polynomial features</span>
          <Badge variant="outline" className="text-[10px]">
            degree {Number(polynomial.degree ?? 2)}
          </Badge>
          {(polynomial.columns as string[] | undefined)?.length ? (
            <span className="text-xs text-muted-foreground">
              ({(polynomial.columns as string[]).length} columns)
            </span>
          ) : null}
        </div>
      )}

      {interEnabled && interactions && (
        <div className="flex items-center gap-2 text-sm">
          <Combine className="h-4 w-4 text-green-500" />
          <span>Interaction features</span>
          {(interactions.column_pairs as unknown[] | undefined)?.length ? (
            <span className="text-xs text-muted-foreground">
              ({(interactions.column_pairs as unknown[]).length} pairs)
            </span>
          ) : null}
        </div>
      )}
    </div>
  );
}
