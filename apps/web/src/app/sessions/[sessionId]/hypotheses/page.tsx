"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useUpdateSession } from "@/hooks/use-session";
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
import {
  ArrowRight,
  CheckCircle,
  XCircle,
  Lightbulb,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";
import type { Hypothesis } from "@/types/api";

export default function HypothesesPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;
  const queryClient = useQueryClient();
  const updateSession = useUpdateSession(sessionId);

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
    }) => api.patch(`/hypotheses/${id}`, { status }),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["hypotheses", sessionId],
      }),
  });

  function handleRun() {
    updateSession.mutate(
      { current_step: "hypothesis-results" },
      {
        onSuccess: () => {
          toast.success("Running hypothesis tests...");
          router.push(`/sessions/${sessionId}/hypothesis-results`);
        },
      },
    );
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

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Hypotheses</h2>
        <p className="text-muted-foreground">
          Review AI-generated hypotheses. Approve or reject each one before
          running the tests.
        </p>
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
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant={hyp.status === "approved" ? "default" : "outline"}
                  className="gap-1"
                  onClick={() =>
                    updateHypothesis.mutate({
                      id: hyp.id,
                      status: "approved",
                    })
                  }
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
                  onClick={() =>
                    updateHypothesis.mutate({
                      id: hyp.id,
                      status: "rejected",
                    })
                  }
                  disabled={updateHypothesis.isPending}
                >
                  <XCircle className="h-3.5 w-3.5" />
                  Reject
                </Button>
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
          disabled={updateSession.isPending}
        >
          {updateSession.isPending ? (
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
