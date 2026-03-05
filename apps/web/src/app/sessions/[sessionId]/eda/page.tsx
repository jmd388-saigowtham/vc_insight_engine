"use client";

import { useParams, useRouter } from "next/navigation";
import { useArtifacts } from "@/hooks/use-artifacts";
import { useUpdateSession } from "@/hooks/use-session";
import { ChartGrid } from "@/components/charts/chart-grid";
import { Button } from "@/components/ui/button";
import { ArrowRight, Loader2 } from "lucide-react";

export default function EdaPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;
  const { data: artifacts, isLoading } = useArtifacts(sessionId, "eda");
  const updateSession = useUpdateSession(sessionId);

  function handleContinue() {
    updateSession.mutate(
      { current_step: "hypotheses" },
      {
        onSuccess: () =>
          router.push(`/sessions/${sessionId}/hypotheses`),
      },
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Exploratory Data Analysis</h2>
        <p className="text-muted-foreground">
          AI-generated visualizations including distributions, correlations, and
          feature importance plots.
        </p>
      </div>

      <ChartGrid artifacts={artifacts ?? []} loading={isLoading} />

      {artifacts && artifacts.length > 0 && (
        <Button
          className="gap-2"
          size="lg"
          onClick={handleContinue}
          disabled={updateSession.isPending}
        >
          {updateSession.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ArrowRight className="h-4 w-4" />
          )}
          Continue to Hypotheses
        </Button>
      )}
    </div>
  );
}
