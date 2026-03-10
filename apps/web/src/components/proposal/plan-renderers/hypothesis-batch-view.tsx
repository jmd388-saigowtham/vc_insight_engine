"use client";

import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { FlaskConical } from "lucide-react";

interface HypothesisBatchViewProps {
  plan: Record<string, unknown>;
}

export function HypothesisBatchView({ plan }: HypothesisBatchViewProps) {
  const hypotheses = (plan.hypotheses ?? []) as Array<{
    id?: string;
    statement: string;
    test_type: string;
    variables?: string[];
    expected_outcome?: string;
  }>;
  const focusAreas = plan.focus_areas as string[] | undefined;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <FlaskConical className="h-4 w-4 text-indigo-500" />
        <span className="text-sm font-medium">
          {hypotheses.length} hypothesis tests
        </span>
      </div>

      {focusAreas && focusAreas.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {focusAreas.map((area) => (
            <Badge key={area} variant="outline" className="text-[10px]">
              {area}
            </Badge>
          ))}
        </div>
      )}

      <ScrollArea className="max-h-40">
        <div className="space-y-1.5">
          {hypotheses.map((h, i) => (
            <div key={h.id ?? i} className="rounded border p-2 text-xs">
              <p className="font-medium">{h.statement}</p>
              <div className="mt-1 flex gap-2 text-muted-foreground">
                <Badge variant="secondary" className="text-[10px]">
                  {h.test_type}
                </Badge>
                {h.variables && h.variables.length > 0 && (
                  <span>{h.variables.join(", ")}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
