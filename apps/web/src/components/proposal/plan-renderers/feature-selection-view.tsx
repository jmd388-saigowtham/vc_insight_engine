"use client";

import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { CheckCircle, XCircle } from "lucide-react";

interface FeatureSelectionViewProps {
  plan: Record<string, unknown>;
}

export function FeatureSelectionView({ plan }: FeatureSelectionViewProps) {
  const features = (plan.features ?? []) as Array<{
    name: string;
    importance?: number;
    reasoning?: string;
    selected?: boolean;
  }>;
  const selectedCount = features.filter((f) => f.selected !== false).length;

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        {selectedCount} of {features.length} features selected
      </p>
      <ScrollArea className="max-h-48">
        <div className="space-y-1">
          {features.map((f) => {
            const selected = f.selected !== false;
            return (
              <div
                key={f.name}
                className="flex items-center gap-2 rounded px-2 py-1 text-xs hover:bg-muted/50"
              >
                {selected ? (
                  <CheckCircle className="h-3.5 w-3.5 shrink-0 text-green-500" />
                ) : (
                  <XCircle className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                )}
                <span className={selected ? "font-medium" : "text-muted-foreground"}>
                  {f.name}
                </span>
                {f.importance !== undefined && (
                  <Badge variant="outline" className="ml-auto text-[10px]">
                    {(f.importance * 100).toFixed(0)}%
                  </Badge>
                )}
                {f.reasoning && (
                  <span className="ml-1 text-[10px] text-muted-foreground truncate max-w-[200px]">
                    {f.reasoning}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
