"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useTraceStore } from "@/stores/trace-store";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { TraceEventItem } from "./trace-event-item";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import type { EventType } from "@/types/event";

const AI_SUMMARY_TYPES: EventType[] = [
  "DECISION",
  "AI_REASONING",
  "MODEL_SELECTION",
  "FINAL_SUMMARY",
  "PROPOSAL_CREATED",
  "PROPOSAL_APPROVED",
  "PROPOSAL_REVISED",
  "PROPOSAL_REJECTED",
  "OBSERVATION",
  "REFLECTION",
  "STAGE_RUNNING",
  "STAGE_DONE",
];

type TabValue = "all" | "ai-summary";

export function LiveTraceSidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [activeTab, setActiveTab] = useState<TabValue>("all");
  const events = useTraceStore((s) => s.events);
  const isConnected = useTraceStore((s) => s.isConnected);
  const scrollRef = useRef<HTMLDivElement>(null);

  const filteredEvents = useMemo(() => {
    if (activeTab === "ai-summary") {
      return events.filter((e) => AI_SUMMARY_TYPES.includes(e.event_type));
    }
    return events;
  }, [events, activeTab]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredEvents.length]);

  if (collapsed) {
    return (
      <div className="border-l bg-card p-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed(false)}
        >
          <PanelRightOpen className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <aside className="flex w-80 shrink-0 flex-col border-l bg-card">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              isConnected ? "bg-green-500" : "bg-red-500",
            )}
          />
          <span className="text-sm font-medium">Live Trace</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => setCollapsed(true)}
        >
          <PanelRightClose className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex border-b">
        <button
          className={cn(
            "flex-1 px-3 py-1.5 text-xs font-medium transition-colors",
            activeTab === "all"
              ? "border-b-2 border-primary text-primary"
              : "text-muted-foreground hover:text-foreground",
          )}
          onClick={() => setActiveTab("all")}
        >
          All Events
        </button>
        <button
          className={cn(
            "flex-1 px-3 py-1.5 text-xs font-medium transition-colors",
            activeTab === "ai-summary"
              ? "border-b-2 border-primary text-primary"
              : "text-muted-foreground hover:text-foreground",
          )}
          onClick={() => setActiveTab("ai-summary")}
        >
          AI Summary
        </button>
      </div>

      <ScrollArea className="flex-1">
        <div ref={scrollRef} className="space-y-0.5 p-2">
          {filteredEvents.length === 0 ? (
            <p className="py-8 text-center text-xs text-muted-foreground">
              {activeTab === "ai-summary"
                ? "No AI summary events yet..."
                : "Waiting for events..."}
            </p>
          ) : (
            filteredEvents.map((event) => (
              <TraceEventItem key={event.id} event={event} />
            ))
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}
