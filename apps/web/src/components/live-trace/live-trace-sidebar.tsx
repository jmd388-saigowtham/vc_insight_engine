"use client";

import { useEffect, useRef, useState } from "react";
import { useTraceStore } from "@/stores/trace-store";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { TraceEventItem } from "./trace-event-item";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import { cn } from "@/lib/utils";

export function LiveTraceSidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const events = useTraceStore((s) => s.events);
  const isConnected = useTraceStore((s) => s.isConnected);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events.length]);

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

      <ScrollArea className="flex-1">
        <div ref={scrollRef} className="space-y-0.5 p-2">
          {events.length === 0 ? (
            <p className="py-8 text-center text-xs text-muted-foreground">
              Waiting for events...
            </p>
          ) : (
            events.map((event) => (
              <TraceEventItem key={event.id} event={event} />
            ))
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}
