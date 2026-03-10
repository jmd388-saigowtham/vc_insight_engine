"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useWizardNavigation } from "@/hooks/use-wizard-navigation";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ArrowRight,
  CheckCircle,
  XCircle,
  Lightbulb,
  Loader2,
  Plus,
  CheckCheck,
  XOctagon,
} from "lucide-react";
import { toast } from "sonner";
import type { Hypothesis } from "@/types/api";
import { PendingProposals } from "@/components/proposal/pending-proposals";
import { useStepStates } from "@/hooks/use-step-states";
import { StepStatusBanner } from "@/components/step-status-banner";

const TEST_TYPES = [
  { value: "t_test", label: "T-Test" },
  { value: "chi_square", label: "Chi-Square" },
  { value: "correlation", label: "Correlation" },
  { value: "anova", label: "ANOVA" },
  { value: "mann_whitney", label: "Mann-Whitney U" },
];

export default function HypothesesPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const queryClient = useQueryClient();
  const { navigateToNext, isPending } = useWizardNavigation("hypotheses");
  const { data: stepStates } = useStepStates(sessionId);
  const hypothesisState = stepStates?.hypothesis ?? "NOT_STARTED";

  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  const [customDialogOpen, setCustomDialogOpen] = useState(false);
  const [customStatement, setCustomStatement] = useState("");
  const [customTestType, setCustomTestType] = useState("");
  const [customVariables, setCustomVariables] = useState("");

  const { data: hypotheses, isLoading } = useQuery({
    queryKey: ["hypotheses", sessionId],
    queryFn: () =>
      api.get<Hypothesis[]>(`/sessions/${sessionId}/hypotheses`),
  });

  const updateHypothesis = useMutation({
    mutationFn: ({
      id,
      status,
    }: {
      id: string;
      status: "approved" | "rejected";
      reason?: string;
    }) => api.patch(`/hypotheses/${id}`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["hypotheses", sessionId],
      });
      setRejectingId(null);
      setRejectionReason("");
    },
  });

  const batchUpdateMutation = useMutation({
    mutationFn: (status: "approved" | "rejected") =>
      api.post(`/sessions/${sessionId}/feedback`, {
        message: `User ${status} all pending hypotheses. Please ${status === "approved" ? "execute" : "skip"} them.`,
        step: "hypothesis",
      }),
    onSuccess: (_, status) => {
      toast.success(
        status === "approved"
          ? "Hypotheses approved for testing"
          : "Hypotheses rejected",
      );
      queryClient.invalidateQueries({
        queryKey: ["proposals", "pending", sessionId],
      });
      queryClient.invalidateQueries({
        queryKey: ["hypotheses", sessionId],
      });
    },
    onError: () => {
      toast.error("Batch update failed");
    },
  });

  const addCustomHypothesis = useMutation({
    mutationFn: (data: {
      statement: string;
      test_type: string;
      variables: string[];
    }) =>
      api.post(`/sessions/${sessionId}/feedback`, {
        message: `Add custom hypothesis: "${data.statement}" using ${data.test_type} test with variables: ${data.variables.join(", ")}.`,
        step: "hypothesis",
      }),
    onSuccess: () => {
      toast.success("Custom hypothesis submitted — the AI will incorporate it");
      setCustomDialogOpen(false);
      setCustomStatement("");
      setCustomTestType("");
      setCustomVariables("");
      queryClient.invalidateQueries({
        queryKey: ["proposals", "pending", sessionId],
      });
    },
    onError: () => {
      toast.error("Failed to submit hypothesis");
    },
  });

  function handleReject(id: string) {
    if (rejectingId === id && rejectionReason.trim()) {
      updateHypothesis.mutate({
        id,
        status: "rejected",
        reason: rejectionReason.trim(),
      });
    } else if (rejectingId === id) {
      updateHypothesis.mutate({ id, status: "rejected" });
    } else {
      setRejectingId(id);
      setRejectionReason("");
    }
  }

  function handleAddCustom() {
    if (!customStatement.trim() || !customTestType) return;
    const variables = customVariables
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
    addCustomHypothesis.mutate({
      statement: customStatement.trim(),
      test_type: customTestType,
      variables,
    });
  }

  function handleRun() {
    toast.success("Running hypothesis tests...");
    navigateToNext("hypothesis-results");
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-32 w-full" />
        ))}
      </div>
    );
  }

  const approvedCount =
    hypotheses?.filter((h) => h.status === "approved").length ?? 0;
  const hasPending = (hypotheses ?? []).some((h) => h.status === "pending");

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Hypotheses</h2>
        <p className="text-muted-foreground">
          Review AI-generated hypotheses. Approve or reject each one before
          running the tests.
        </p>
      </div>

      <PendingProposals sessionId={sessionId} step="hypothesis" />
      <StepStatusBanner state={hypothesisState} stepLabel="Hypothesis Testing" />

      {/* Batch actions and Add Custom */}
      <div className="flex flex-wrap items-center gap-2">
        {hasPending && (
          <>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => batchUpdateMutation.mutate("approved")}
              disabled={batchUpdateMutation.isPending}
            >
              {batchUpdateMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <CheckCheck className="h-3.5 w-3.5" />
              )}
              Approve All
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => batchUpdateMutation.mutate("rejected")}
              disabled={batchUpdateMutation.isPending}
            >
              {batchUpdateMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <XOctagon className="h-3.5 w-3.5" />
              )}
              Reject All
            </Button>
          </>
        )}

        <Dialog open={customDialogOpen} onOpenChange={setCustomDialogOpen}>
          <DialogTrigger asChild>
            <Button variant="outline" size="sm" className="gap-1.5 ml-auto">
              <Plus className="h-3.5 w-3.5" />
              Add Custom Hypothesis
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add Custom Hypothesis</DialogTitle>
              <DialogDescription>
                Define a custom hypothesis to test against your data.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label htmlFor="hyp-statement">Hypothesis Statement</Label>
                <Textarea
                  id="hyp-statement"
                  placeholder="e.g., Customers with higher engagement scores have lower churn rates"
                  value={customStatement}
                  onChange={(e) => setCustomStatement(e.target.value)}
                  rows={3}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="hyp-test-type">Test Type</Label>
                <Select
                  value={customTestType}
                  onValueChange={setCustomTestType}
                >
                  <SelectTrigger id="hyp-test-type">
                    <SelectValue placeholder="Select test type..." />
                  </SelectTrigger>
                  <SelectContent>
                    {TEST_TYPES.map((tt) => (
                      <SelectItem key={tt.value} value={tt.value}>
                        {tt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="hyp-variables">
                  Variables{" "}
                  <span className="text-xs text-muted-foreground">
                    (comma-separated)
                  </span>
                </Label>
                <Input
                  id="hyp-variables"
                  placeholder="e.g., engagement_score, churn_flag"
                  value={customVariables}
                  onChange={(e) => setCustomVariables(e.target.value)}
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                onClick={handleAddCustom}
                disabled={
                  !customStatement.trim() ||
                  !customTestType ||
                  addCustomHypothesis.isPending
                }
                className="gap-2"
              >
                {addCustomHypothesis.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
                Add Hypothesis
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <div className="space-y-3">
        {(hypotheses ?? []).map((hyp) => (
          <Card key={hyp.id}>
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <Lightbulb className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
                  <div>
                    <CardTitle className="text-sm">{hyp.statement}</CardTitle>
                    <CardDescription className="mt-1">
                      Test: {hyp.test_type} | Variables:{" "}
                      {hyp.variables.join(", ")}
                    </CardDescription>
                  </div>
                </div>
                <Badge
                  variant={
                    hyp.status === "approved"
                      ? "default"
                      : hyp.status === "rejected"
                        ? "destructive"
                        : "secondary"
                  }
                >
                  {hyp.status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-sm text-muted-foreground">
                Expected: {hyp.expected_outcome}
              </p>
              <div className="space-y-2">
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant={hyp.status === "approved" ? "default" : "outline"}
                    className="gap-1"
                    onClick={() => {
                      updateHypothesis.mutate({
                        id: hyp.id,
                        status: "approved",
                      });
                      if (rejectingId === hyp.id) setRejectingId(null);
                    }}
                    disabled={updateHypothesis.isPending}
                  >
                    <CheckCircle className="h-3.5 w-3.5" />
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant={
                      hyp.status === "rejected" ? "destructive" : "outline"
                    }
                    className="gap-1"
                    onClick={() => handleReject(hyp.id)}
                    disabled={updateHypothesis.isPending}
                  >
                    <XCircle className="h-3.5 w-3.5" />
                    Reject
                  </Button>
                  {rejectingId === hyp.id && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-xs"
                      onClick={() => {
                        setRejectingId(null);
                        setRejectionReason("");
                      }}
                    >
                      Cancel
                    </Button>
                  )}
                </div>
                {rejectingId === hyp.id && (
                  <div className="flex items-start gap-2">
                    <Textarea
                      placeholder="Reason for rejection (optional)..."
                      value={rejectionReason}
                      onChange={(e) => setRejectionReason(e.target.value)}
                      rows={2}
                      className="text-xs"
                    />
                    <Button
                      size="sm"
                      variant="destructive"
                      className="shrink-0"
                      onClick={() => handleReject(hyp.id)}
                      disabled={updateHypothesis.isPending}
                    >
                      {updateHypothesis.isPending ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        "Confirm"
                      )}
                    </Button>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {approvedCount > 0 && (
        <Button
          className="gap-2"
          size="lg"
          onClick={handleRun}
          disabled={isPending}
        >
          {isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ArrowRight className="h-4 w-4" />
          )}
          Run {approvedCount} Hypotheses
        </Button>
      )}
    </div>
  );
}
