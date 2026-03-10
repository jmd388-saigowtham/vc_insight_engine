"use client";

import { useState } from "react";
import { useParams, usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useSubmitFeedback, useFeedback } from "@/hooks/use-feedback";
import { usePendingProposals } from "@/hooks/use-proposals";
import { api } from "@/lib/api-client";
import {
  MessageSquare,
  Send,
  ChevronDown,
  ChevronUp,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";

function getCurrentStep(pathname: string): string {
  const segments = pathname.split("/");
  return segments[segments.length - 1] || "";
}

export function FeedbackInput() {
  const params = useParams();
  const pathname = usePathname();
  const sessionId = params.sessionId as string;
  const step = getCurrentStep(pathname);

  const [isOpen, setIsOpen] = useState(false);
  const [message, setMessage] = useState("");

  const submitMutation = useSubmitFeedback(sessionId);
  const { data: recentFeedback } = useFeedback(sessionId, step);
  const { data: pendingProposals } = usePendingProposals(sessionId, step);
  const queryClient = useQueryClient();

  const hasPendingProposal = pendingProposals && pendingProposals.length > 0;
  const activeProposal = hasPendingProposal ? pendingProposals[0] : null;

  async function handleSubmit() {
    if (!message.trim()) {
      toast.error("Please enter feedback");
      return;
    }
    try {
      if (activeProposal) {
        // Revise the pending proposal with feedback
        await api.post(`/proposals/${activeProposal.id}/revise`, {
          feedback: message.trim(),
        });
        // Resume the agent to regenerate
        await api.post(`/sessions/${sessionId}/resume`, {
          proposal_id: activeProposal.id,
          proposal_type: "business",
        });
        queryClient.invalidateQueries({
          queryKey: ["proposals", "pending", sessionId],
        });
        toast.success("Revision submitted — AI is regenerating the proposal");
      } else {
        await submitMutation.mutateAsync({
          message: message.trim(),
          step: step || undefined,
        });
        toast.success("Feedback submitted");
      }
      setMessage("");
    } catch {
      toast.error("Failed to submit feedback");
    }
  }

  const STATUS_BADGE: Record<string, string> = {
    pending: "bg-amber-500",
    acknowledged: "bg-blue-500",
    applied: "bg-green-500",
  };

  return (
    <div className="fixed bottom-4 right-4 z-40 w-80">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between rounded-t-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4" />
          Tell the AI...
        </div>
        {isOpen ? (
          <ChevronDown className="h-4 w-4" />
        ) : (
          <ChevronUp className="h-4 w-4" />
        )}
      </button>

      {isOpen && (
        <div className="rounded-b-md border border-t-0 bg-background p-3 shadow-lg space-y-2">
          <Textarea
            placeholder={
              hasPendingProposal
                ? "Tell the AI what to change about this proposal..."
                : "Tell the AI what to change..."
            }
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            className="min-h-[60px] text-xs resize-none"
            disabled={submitMutation.isPending}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                handleSubmit();
              }
            }}
          />
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              {step && (
                <Badge variant="outline" className="text-[10px]">
                  {step}
                </Badge>
              )}
              {hasPendingProposal && (
                <Badge
                  variant="outline"
                  className="text-[10px] border-primary/50 text-primary"
                >
                  Revising proposal
                </Badge>
              )}
            </div>
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={submitMutation.isPending || !message.trim()}
              className="ml-auto"
            >
              {submitMutation.isPending ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : (
                <Send className="mr-1 h-3 w-3" />
              )}
              Send
            </Button>
          </div>

          {recentFeedback && recentFeedback.length > 0 && (
            <div className="border-t pt-2 space-y-1">
              <p className="text-[10px] font-medium text-muted-foreground">Recent</p>
              {recentFeedback.slice(0, 3).map((fb) => (
                <div
                  key={fb.id}
                  className="flex items-start gap-1.5 text-[10px] text-muted-foreground"
                >
                  <Badge
                    className={`${STATUS_BADGE[fb.status] ?? "bg-gray-500"} text-white text-[8px] px-1 py-0 shrink-0`}
                  >
                    {fb.status}
                  </Badge>
                  <span className="truncate">{fb.message}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
