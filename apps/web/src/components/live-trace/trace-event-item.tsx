"use client";

import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  FileCode,
  Play,
  Square,
  AlertCircle,
  Info,
  Wrench,
  CheckCircle,
  Brain,
  ChevronDown,
} from "lucide-react";
import type { TraceEvent, EventType } from "@/types/event";

const EVENT_CONFIG: Record<
  EventType,
  { icon: typeof Info; color: string; bgColor: string }
> = {
  PLAN: { icon: Brain, color: "text-blue-500", bgColor: "bg-blue-500/10" },
  TOOL_CALL: {
    icon: Wrench,
    color: "text-purple-500",
    bgColor: "bg-purple-500/10",
  },
  TOOL_RESULT: {
    icon: CheckCircle,
    color: "text-green-500",
    bgColor: "bg-green-500/10",
  },
  CODE_PROPOSED: {
    icon: FileCode,
    color: "text-amber-500",
    bgColor: "bg-amber-500/10",
  },
  CODE_APPROVED: {
    icon: CheckCircle,
    color: "text-green-500",
    bgColor: "bg-green-500/10",
  },
  CODE_DENIED: {
    icon: AlertCircle,
    color: "text-red-500",
    bgColor: "bg-red-500/10",
  },
  EXEC_START: {
    icon: Play,
    color: "text-blue-500",
    bgColor: "bg-blue-500/10",
  },
  EXEC_END: {
    icon: Square,
    color: "text-gray-500",
    bgColor: "bg-gray-500/10",
  },
  ERROR: {
    icon: AlertCircle,
    color: "text-red-500",
    bgColor: "bg-red-500/10",
  },
  INFO: { icon: Info, color: "text-sky-500", bgColor: "bg-sky-500/10" },
  STEP_START: {
    icon: Play,
    color: "text-indigo-500",
    bgColor: "bg-indigo-500/10",
  },
  STEP_END: {
    icon: Square,
    color: "text-indigo-500",
    bgColor: "bg-indigo-500/10",
  },
};

export function TraceEventItem({ event }: { event: TraceEvent }) {
  const [open, setOpen] = useState(false);
  const config = EVENT_CONFIG[event.event_type];
  const Icon = config.icon;

  const hasPayload =
    event.payload && Object.keys(event.payload).length > 0;

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted/50">
        <span className={cn("mt-0.5 shrink-0", config.color)}>
          <Icon className="h-3.5 w-3.5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <Badge
              variant="outline"
              className={cn("px-1 py-0 text-[10px]", config.bgColor, config.color)}
            >
              {event.event_type}
            </Badge>
            <span className="truncate text-muted-foreground">
              {event.step}
            </span>
          </div>
          <span className="text-[10px] text-muted-foreground">
            {formatDistanceToNow(new Date(event.created_at), {
              addSuffix: true,
            })}
          </span>
        </div>
        {hasPayload && (
          <ChevronDown
            className={cn(
              "h-3 w-3 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-180",
            )}
          />
        )}
      </CollapsibleTrigger>
      {hasPayload && (
        <CollapsibleContent>
          <pre className="mx-2 mb-1 max-h-40 overflow-auto rounded bg-muted/50 p-2 text-[10px] leading-relaxed">
            {JSON.stringify(event.payload, null, 2)}
          </pre>
        </CollapsibleContent>
      )}
    </Collapsible>
  );
}
