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
  Compass,
  Edit3,
  Image,
  AlertTriangle,
  User,
  RefreshCw,
  Lightbulb,
  BarChart3,
  FileText,
  FileEdit,
  Search,
  Copy,
  RotateCcw,
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
  DECISION: {
    icon: Compass,
    color: "text-teal-500",
    bgColor: "bg-teal-500/10",
  },
  CODE_EDITED: {
    icon: Edit3,
    color: "text-amber-500",
    bgColor: "bg-amber-500/10",
  },
  ARTIFACT: {
    icon: Image,
    color: "text-emerald-500",
    bgColor: "bg-emerald-500/10",
  },
  WARNING: {
    icon: AlertTriangle,
    color: "text-yellow-500",
    bgColor: "bg-yellow-500/10",
  },
  USER_INPUT: {
    icon: User,
    color: "text-blue-500",
    bgColor: "bg-blue-500/10",
  },
  STEP_STALE: {
    icon: RefreshCw,
    color: "text-orange-500",
    bgColor: "bg-orange-500/10",
  },
  AI_REASONING: {
    icon: Lightbulb,
    color: "text-purple-500",
    bgColor: "bg-purple-500/10",
  },
  TOOL_DISCOVERY: {
    icon: Search,
    color: "text-yellow-500",
    bgColor: "bg-yellow-500/10",
  },
  CODE_REUSE: {
    icon: Copy,
    color: "text-indigo-500",
    bgColor: "bg-indigo-500/10",
  },
  DOC_UPDATED: {
    icon: FileEdit,
    color: "text-gray-500",
    bgColor: "bg-gray-500/10",
  },
  ARTIFACT_CREATED: {
    icon: Image,
    color: "text-cyan-500",
    bgColor: "bg-cyan-500/10",
  },
  MODEL_SELECTION: {
    icon: BarChart3,
    color: "text-green-500",
    bgColor: "bg-green-500/10",
  },
  STAGE_RERUN: {
    icon: RotateCcw,
    color: "text-orange-500",
    bgColor: "bg-orange-500/10",
  },
  FINAL_SUMMARY: {
    icon: FileText,
    color: "text-emerald-500",
    bgColor: "bg-emerald-500/10",
  },
  PROPOSAL_CREATED: {
    icon: Lightbulb,
    color: "text-amber-500",
    bgColor: "bg-amber-500/10",
  },
  PROPOSAL_APPROVED: {
    icon: CheckCircle,
    color: "text-green-500",
    bgColor: "bg-green-500/10",
  },
  PROPOSAL_REVISED: {
    icon: Edit3,
    color: "text-blue-500",
    bgColor: "bg-blue-500/10",
  },
  PROPOSAL_REJECTED: {
    icon: AlertCircle,
    color: "text-red-500",
    bgColor: "bg-red-500/10",
  },
  STAGE_MARKED_STALE: {
    icon: RefreshCw,
    color: "text-orange-500",
    bgColor: "bg-orange-500/10",
  },
  USER_FEEDBACK: {
    icon: User,
    color: "text-blue-500",
    bgColor: "bg-blue-500/10",
  },
  STAGE_RUNNING: {
    icon: Play,
    color: "text-blue-500",
    bgColor: "bg-blue-500/10",
  },
  STAGE_DONE: {
    icon: CheckCircle,
    color: "text-green-500",
    bgColor: "bg-green-500/10",
  },
  OBSERVATION: {
    icon: Search,
    color: "text-cyan-500",
    bgColor: "bg-cyan-500/10",
  },
  REFLECTION: {
    icon: Brain,
    color: "text-violet-500",
    bgColor: "bg-violet-500/10",
  },
  RETRY: {
    icon: RotateCcw,
    color: "text-orange-500",
    bgColor: "bg-orange-500/10",
  },
};

function getSummary(event: TraceEvent): string | null {
  const p = event.payload;
  switch (event.event_type) {
    case "PLAN":
      return typeof p.message === "string" ? p.message : null;
    case "TOOL_CALL":
      return typeof p.server === "string" && typeof p.tool === "string"
        ? `${p.server}.${p.tool}`
        : null;
    case "TOOL_RESULT":
      return p.success === true
        ? "Completed successfully"
        : p.success === false
          ? `Failed${typeof p.error === "string" ? `: ${p.error}` : ""}`
          : null;
    case "DECISION":
      return typeof p.action === "string" ? p.action : null;
    case "AI_REASONING":
      return typeof p.reasoning === "string"
        ? p.reasoning.slice(0, 80) + (p.reasoning.length > 80 ? "..." : "")
        : null;
    case "MODEL_SELECTION":
      return typeof p.chosen_model === "string" ? p.chosen_model : null;
    case "FINAL_SUMMARY":
      return typeof p.title === "string" ? p.title : "Pipeline Summary";
    case "PROPOSAL_CREATED":
      return typeof p.summary === "string" ? p.summary : "New AI proposal";
    case "PROPOSAL_APPROVED":
      return `Proposal approved (${typeof p.proposal_type === "string" ? p.proposal_type : "plan"})`;
    case "PROPOSAL_REVISED":
      return `Revision requested${typeof p.feedback === "string" ? `: ${p.feedback.slice(0, 40)}...` : ""}`;
    case "PROPOSAL_REJECTED":
      return "Proposal rejected";
    case "USER_FEEDBACK":
      return typeof p.message === "string" ? p.message.slice(0, 60) : "User feedback";
    case "STAGE_RUNNING":
      return typeof p.message === "string" ? p.message : "Stage running...";
    case "STAGE_DONE":
      return typeof p.message === "string" ? p.message : "Stage completed";
    case "OBSERVATION":
      return typeof p.message === "string" ? p.message.slice(0, 80) : "Observing results";
    case "REFLECTION":
      return typeof p.message === "string" ? p.message.slice(0, 80) : "Reflecting on outcome";
    case "RETRY":
      return typeof p.message === "string" ? p.message : "Retrying...";
    default:
      return null;
  }
}

function renderPayloadContent(event: TraceEvent) {
  const p = event.payload;

  switch (event.event_type) {
    case "PLAN":
      if (typeof p.message === "string") {
        return (
          <p className="mx-2 mb-1 rounded bg-muted/50 p-2 text-[10px] leading-relaxed text-foreground">
            {p.message}
          </p>
        );
      }
      break;
    case "DECISION":
      return (
        <div className="mx-2 mb-1 space-y-1 rounded bg-muted/50 p-2 text-[10px] leading-relaxed">
          {typeof p.step === "string" && (
            <Badge variant="outline" className="mb-1 text-[9px] px-1 py-0 text-teal-500 bg-teal-500/10">
              {p.step}
            </Badge>
          )}
          {typeof p.action === "string" && (
            <p>
              <span className="font-medium text-teal-500">Action:</span>{" "}
              {p.action}
            </p>
          )}
          {typeof p.reasoning === "string" && (
            <p>
              <span className="font-medium text-muted-foreground">Reasoning:</span>{" "}
              {p.reasoning}
            </p>
          )}
        </div>
      );
    case "AI_REASONING":
      return (
        <blockquote className="mx-2 mb-1 rounded border-l-2 border-purple-500 bg-purple-500/5 p-2 text-[10px] italic leading-relaxed text-foreground">
          {typeof p.reasoning === "string" ? p.reasoning : JSON.stringify(p, null, 2)}
        </blockquote>
      );
    case "MODEL_SELECTION":
      return (
        <div className="mx-2 mb-1 space-y-1 rounded bg-muted/50 p-2 text-[10px] leading-relaxed">
          {typeof p.chosen_model === "string" && (
            <p>
              <span className="font-medium text-green-500">Selected:</span>{" "}
              {p.chosen_model}
            </p>
          )}
          {Array.isArray(p.models) && (
            <div className="flex flex-wrap gap-1 mt-1">
              {(p.models as string[]).map((m) => (
                <Badge
                  key={m}
                  variant="outline"
                  className={cn(
                    "text-[9px] px-1 py-0",
                    m === p.chosen_model
                      ? "text-green-500 bg-green-500/10 font-semibold"
                      : "text-muted-foreground",
                  )}
                >
                  {m}
                </Badge>
              ))}
            </div>
          )}
          {typeof p.reasoning === "string" && (
            <p className="mt-1 text-muted-foreground">{p.reasoning}</p>
          )}
        </div>
      );
    case "FINAL_SUMMARY":
      return (
        <div className="mx-2 mb-1 rounded border border-emerald-500/30 bg-emerald-500/5 p-3 text-[10px] leading-relaxed">
          {typeof p.title === "string" && (
            <p className="mb-1 font-semibold text-emerald-500">{p.title}</p>
          )}
          {typeof p.summary === "string" && (
            <p className="text-foreground">{p.summary}</p>
          )}
          {Array.isArray(p.key_findings) && (
            <ul className="mt-1 list-disc pl-3 text-muted-foreground">
              {(p.key_findings as string[]).map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
        </div>
      );
    case "TOOL_CALL":
    case "TOOL_RESULT":
      return (
        <div className="mx-2 mb-1 space-y-1 rounded bg-muted/50 p-2 text-[10px] leading-relaxed">
          {typeof p.server === "string" && (
            <p>
              <span className="font-medium text-purple-500">Server:</span>{" "}
              {p.server}
            </p>
          )}
          {typeof p.tool === "string" && (
            <p>
              <span className="font-medium text-purple-500">Tool:</span>{" "}
              {p.tool}
            </p>
          )}
          {event.event_type === "TOOL_RESULT" && typeof p.success === "boolean" && (
            <p>
              <span className="font-medium text-muted-foreground">Status:</span>{" "}
              <span className={p.success ? "text-green-500" : "text-red-500"}>
                {p.success ? "Success" : "Failed"}
              </span>
            </p>
          )}
          {typeof p.error === "string" && (
            <p className="text-red-500">{p.error}</p>
          )}
          {p.args != null && (
            <pre className="mt-1 max-h-24 overflow-auto text-muted-foreground">
              {JSON.stringify(p.args, null, 2)}
            </pre>
          )}
        </div>
      );
  }

  return (
    <pre className="mx-2 mb-1 max-h-40 overflow-auto rounded bg-muted/50 p-2 text-[10px] leading-relaxed">
      {JSON.stringify(p, null, 2)}
    </pre>
  );
}

export function TraceEventItem({ event }: { event: TraceEvent }) {
  const [open, setOpen] = useState(false);
  const config = EVENT_CONFIG[event.event_type];
  const Icon = config.icon;

  const hasPayload =
    event.payload && Object.keys(event.payload).length > 0;
  const summary = getSummary(event);

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
              {summary ?? event.step}
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
          {renderPayloadContent(event)}
        </CollapsibleContent>
      )}
    </Collapsible>
  );
}
