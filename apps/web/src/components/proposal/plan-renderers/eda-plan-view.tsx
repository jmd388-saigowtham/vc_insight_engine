"use client";

import { Badge } from "@/components/ui/badge";
import { BarChart3 } from "lucide-react";

interface EdaPlanViewProps {
  plan: Record<string, unknown>;
}

const PLOT_LABELS: Record<string, string> = {
  distribution_plot: "Distribution",
  correlation_matrix: "Correlation Matrix",
  target_analysis: "Target Analysis",
  box_plot: "Box Plot",
  scatter_plot: "Scatter Plot",
};

export function EdaPlanView({ plan }: EdaPlanViewProps) {
  const plots = (plan.plots ?? []) as Array<{
    type: string;
    params?: Record<string, unknown>;
    reasoning?: string;
  }>;
  const totalPlots = plan.total_plots as number | undefined;

  // Group by type for compact display
  const typeCounts: Record<string, number> = {};
  for (const p of plots) {
    typeCounts[p.type] = (typeCounts[p.type] ?? 0) + 1;
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <BarChart3 className="h-4 w-4 text-blue-500" />
        <span className="text-sm font-medium">
          {totalPlots ?? plots.length} EDA plots
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {Object.entries(typeCounts).map(([type, count]) => (
          <Badge key={type} variant="secondary" className="text-xs">
            {count}x {PLOT_LABELS[type] ?? type}
          </Badge>
        ))}
      </div>

      {plots.length > 0 && plots[0].reasoning && (
        <div className="text-xs text-muted-foreground mt-1">
          {plots.slice(0, 3).map((p, i) => (
            <p key={i} className="truncate">
              <span className="font-medium">{PLOT_LABELS[p.type] ?? p.type}:</span>{" "}
              {p.reasoning}
            </p>
          ))}
          {plots.length > 3 && (
            <p className="text-[10px]">+{plots.length - 3} more...</p>
          )}
        </div>
      )}
    </div>
  );
}
