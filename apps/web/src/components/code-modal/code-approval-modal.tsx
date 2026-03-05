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
import { CheckCircle, XCircle, Edit3, Loader2 } from "lucide-react";
import { toast } from "sonner";

export function CodeApprovalModal() {
  const { isOpen, proposal, closeModal } = useModalStore();
  const [executing, setExecuting] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  if (!proposal) return null;

  async function handleApprove() {
    if (!proposal) return;
    setExecuting(true);
    setLogs(["Starting execution..."]);
    try {
      const result = await api.post<{ stdout: string; stderr: string }>(
        `/sessions/${proposal.session_id}/code/${proposal.id}/approve`,
      );
      setLogs((prev) => [
        ...prev,
        result.stdout || "(no stdout)",
        result.stderr ? `STDERR: ${result.stderr}` : "",
        "Execution completed.",
      ]);
      toast.success("Code executed successfully");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Execution failed";
      setLogs((prev) => [...prev, `ERROR: ${message}`]);
      toast.error("Execution failed");
    } finally {
      setExecuting(false);
    }
  }

  async function handleDeny() {
    if (!proposal) return;
    try {
      await api.post(
        `/sessions/${proposal.session_id}/code/${proposal.id}/deny`,
      );
      toast.info("Code denied");
      closeModal();
    } catch {
      toast.error("Failed to deny code");
    }
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

        <div className="flex-1 min-h-0">
          <MonacoEditor
            height="100%"
            language={languageMap[proposal.language] || "python"}
            value={proposal.code}
            theme="vs-dark"
            options={{
              readOnly: true,
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

        <DialogFooter className="gap-2">
          <Button
            variant="destructive"
            onClick={handleDeny}
            disabled={executing}
          >
            <XCircle className="mr-1.5 h-4 w-4" />
            Deny
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              toast.info("Request changes feature coming soon");
            }}
            disabled={executing}
          >
            <Edit3 className="mr-1.5 h-4 w-4" />
            Request Changes
          </Button>
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
            Approve & Run
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
