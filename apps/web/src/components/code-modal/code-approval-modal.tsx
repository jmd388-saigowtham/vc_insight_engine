"use client";

import { useState } from "react";
import { useModalStore } from "@/stores/modal-store";
import { api } from "@/lib/api-client";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import MonacoEditor from "./monaco-editor";
import { Textarea } from "@/components/ui/textarea";
import { CheckCircle, XCircle, Edit3, Loader2, Lightbulb, Wrench, MessageSquare } from "lucide-react";
import { toast } from "sonner";

export function CodeApprovalModal() {
  const { isOpen, proposal, context, closeModal } = useModalStore();
  const [executing, setExecuting] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [editing, setEditing] = useState(false);
  const [editedCode, setEditedCode] = useState("");
  const [showRevisionInput, setShowRevisionInput] = useState(false);
  const [revisionFeedback, setRevisionFeedback] = useState("");

  if (!proposal) return null;

  async function resumePipeline() {
    if (!proposal) return;
    try {
      await api.post(`/sessions/${proposal.session_id}/resume`, {
        proposal_id: proposal.id,
      });
    } catch {
      // Resume is best-effort; pipeline may already be running
    }
  }

  async function handleApprove() {
    if (!proposal) return;
    setExecuting(true);
    setLogs(["Starting execution..."]);
    try {
      const codeToApprove = editing ? editedCode : undefined;
      const result = await api.post<{ stdout: string; stderr: string }>(
        `/code/${proposal.id}/approve`,
        codeToApprove !== undefined ? { code: codeToApprove } : undefined,
      );
      setLogs((prev) => [
        ...prev,
        result.stdout || "(no stdout)",
        result.stderr ? `STDERR: ${result.stderr}` : "",
        "Execution completed.",
      ]);
      toast.success("Code executed successfully");
      await resumePipeline();
      closeModal();
      setEditing(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Execution failed";
      setLogs((prev) => [...prev, `ERROR: ${message}`]);
      toast.error("Execution failed");
    } finally {
      setExecuting(false);
    }
  }

  async function handleDeny(feedback?: string) {
    if (!proposal) return;
    try {
      await api.post(
        `/code/${proposal.id}/deny`,
        feedback ? { feedback } : undefined,
      );
      toast.info(feedback ? "Revision requested" : "Code denied");
      await resumePipeline();
      closeModal();
      setEditing(false);
      setShowRevisionInput(false);
      setRevisionFeedback("");
    } catch {
      toast.error("Failed to deny code");
    }
  }

  function handleRequestChanges() {
    if (!proposal) return;
    setEditedCode(proposal.code);
    setEditing(true);
  }

  function handleRequestRevision() {
    if (!revisionFeedback.trim()) {
      toast.error("Please provide feedback for the AI");
      return;
    }
    handleDeny(revisionFeedback.trim());
  }

  const languageMap: Record<string, string> = {
    python: "python",
    sql: "sql",
    r: "r",
    javascript: "javascript",
  };

  return (
    <Dialog open={isOpen} onOpenChange={() => !executing && closeModal()}>
      <DialogContent className="max-w-4xl h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Code Review: {proposal.step}
            <Badge variant="outline">{proposal.language}</Badge>
          </DialogTitle>
          <DialogDescription>{proposal.description}</DialogDescription>
        </DialogHeader>

        {context && (
          <div className="space-y-2 rounded-md border bg-muted/30 p-3">
            {context.ai_explanation && (
              <div className="flex items-start gap-2 text-xs">
                <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-purple-500" />
                <div>
                  <p className="font-medium text-foreground">Why was this code generated?</p>
                  <p className="mt-0.5 text-muted-foreground">{context.ai_explanation}</p>
                </div>
              </div>
            )}
            {context.tool_tried && (
              <div className="flex items-center gap-2 text-xs">
                <Wrench className="h-3.5 w-3.5 shrink-0 text-amber-500" />
                <span className="text-muted-foreground">Tool attempted:</span>
                <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                  {context.tool_tried}
                </Badge>
                {context.tool_insufficiency && (
                  <span className="text-muted-foreground">
                    — {context.tool_insufficiency}
                  </span>
                )}
              </div>
            )}
            {context.max_denials > 0 && (
              <div className="flex items-center gap-2 text-xs">
                <MessageSquare className="h-3.5 w-3.5 shrink-0 text-blue-500" />
                <span className="text-muted-foreground">
                  Attempt {context.denial_count + 1} of {context.max_denials + 1}
                </span>
                {context.denial_feedback.length > 0 && (
                  <span className="text-muted-foreground">
                    — Previous feedback: &quot;{context.denial_feedback[context.denial_feedback.length - 1]}&quot;
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        <div className="flex-1 min-h-0">
          <MonacoEditor
            height="100%"
            language={languageMap[proposal.language] || "python"}
            value={editing ? editedCode : proposal.code}
            theme="vs-dark"
            onChange={(value) => {
              if (editing && value !== undefined) setEditedCode(value);
            }}
            options={{
              readOnly: !editing,
              minimap: { enabled: false },
              fontSize: 13,
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              wordWrap: "on",
            }}
          />
        </div>

        {logs.length > 0 && (
          <ScrollArea className="h-32 rounded-md border bg-black p-3">
            <pre className="text-xs text-green-400 font-mono">
              {logs.filter(Boolean).join("\n")}
            </pre>
          </ScrollArea>
        )}

        {showRevisionInput && (
          <div className="flex items-end gap-2 rounded-md border bg-muted/30 p-3">
            <Textarea
              placeholder="Describe what the AI should change..."
              value={revisionFeedback}
              onChange={(e) => setRevisionFeedback(e.target.value)}
              className="min-h-[60px] flex-1 text-xs"
              disabled={executing}
            />
            <div className="flex flex-col gap-1">
              <Button
                size="sm"
                onClick={handleRequestRevision}
                disabled={executing}
                className="bg-amber-600 hover:bg-amber-700"
              >
                Send Revision
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setShowRevisionInput(false);
                  setRevisionFeedback("");
                }}
                disabled={executing}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        <DialogFooter className="gap-2">
          <Button
            variant="destructive"
            onClick={() => handleDeny()}
            disabled={executing}
          >
            <XCircle className="mr-1.5 h-4 w-4" />
            Deny
          </Button>
          {!editing && !showRevisionInput && (
            <Button
              variant="outline"
              onClick={() => setShowRevisionInput(true)}
              disabled={executing}
            >
              <MessageSquare className="mr-1.5 h-4 w-4" />
              Request AI Revision
            </Button>
          )}
          {!editing && (
            <Button
              variant="outline"
              onClick={handleRequestChanges}
              disabled={executing}
            >
              <Edit3 className="mr-1.5 h-4 w-4" />
              Edit Manually
            </Button>
          )}
          <Button
            onClick={handleApprove}
            disabled={executing}
            className="bg-green-600 hover:bg-green-700"
          >
            {executing ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle className="mr-1.5 h-4 w-4" />
            )}
            {editing ? "Approve Edited & Run" : "Approve & Run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
