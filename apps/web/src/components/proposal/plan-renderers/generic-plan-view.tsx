"use client";

import { ScrollArea } from "@/components/ui/scroll-area";

interface GenericPlanViewProps {
  plan: Record<string, unknown>;
}

export function GenericPlanView({ plan }: GenericPlanViewProps) {
  return (
    <ScrollArea className="max-h-60">
      <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono rounded-md bg-muted/50 p-3">
        {JSON.stringify(plan, null, 2)}
      </pre>
    </ScrollArea>
  );
}
