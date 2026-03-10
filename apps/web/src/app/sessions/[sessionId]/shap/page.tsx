"use client";

import { useParams } from "next/navigation";
import { useArtifacts } from "@/hooks/use-artifacts";
import { useWizardNavigation } from "@/hooks/use-wizard-navigation";
import { ChartGrid } from "@/components/charts/chart-grid";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowRight, Sparkles, Loader2 } from "lucide-react";
import type { Artifact } from "@/types/api";

export default function ShapPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const { data: artifacts, isLoading } = useArtifacts(sessionId, "shap");
  const { navigateToNext, isPending } = useWizardNavigation("shap");

  const summaryPlot = artifacts?.find((a) =>
    a.title.toLowerCase().includes("summary"),
  );
  const barChart = artifacts?.find(
    (a) =>
      a.title.toLowerCase().includes("importance") && a !== summaryPlot,
  );
  const waterfallPlots =
    artifacts?.filter((a) =>
      a.title.toLowerCase().includes("waterfall"),
    ) ?? [];
  const otherArtifacts =
    artifacts?.filter(
      (a) =>
        a !== summaryPlot &&
        a !== barChart &&
        !waterfallPlots.includes(a),
    ) ?? [];

  function handleContinue() {
    navigateToNext("report");
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const BASE_URL =
    process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">SHAP Explanations</h2>
        <p className="text-muted-foreground">
          Understand which features drive the model predictions using SHAP
          (SHapley Additive exPlanations).
        </p>
      </div>

      {summaryPlot && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary" />
              <div>
                <CardTitle className="text-base">
                  {summaryPlot.title}
                </CardTitle>
                <CardDescription>
                  {summaryPlot.description}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {summaryPlot.file_path && (
              <img
                src={`${BASE_URL}${summaryPlot.file_path}`}
                alt={summaryPlot.title}
                className="w-full rounded-md"
              />
            )}
          </CardContent>
        </Card>
      )}

      {barChart && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{barChart.title}</CardTitle>
            <CardDescription>{barChart.description}</CardDescription>
          </CardHeader>
          <CardContent>
            {barChart.file_path && (
              <img
                src={`${BASE_URL}${barChart.file_path}`}
                alt={barChart.title}
                className="w-full rounded-md"
              />
            )}
          </CardContent>
        </Card>
      )}

      {waterfallPlots.length > 0 && (
        <div>
          <h3 className="mb-3 text-lg font-semibold">
            Individual Predictions
          </h3>
          <ChartGrid artifacts={waterfallPlots} />
        </div>
      )}

      {otherArtifacts.length > 0 && (
        <ChartGrid artifacts={otherArtifacts} />
      )}

      {artifacts && artifacts.length > 0 && (
        <Button
          className="gap-2"
          size="lg"
          onClick={handleContinue}
          disabled={isPending}
        >
          {isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ArrowRight className="h-4 w-4" />
          )}
          Continue to Report
        </Button>
      )}
    </div>
  );
}
