"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ArrowRight, BarChart3, Brain, FileSpreadsheet } from "lucide-react";

export default function HomePage() {
  const router = useRouter();

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-background via-background to-primary/5">
      <div className="mx-auto max-w-3xl px-4 text-center">
        <div className="mb-8 flex justify-center">
          <div className="rounded-2xl bg-primary/10 p-4">
            <BarChart3 className="h-12 w-12 text-primary" />
          </div>
        </div>

        <h1 className="mb-4 text-5xl font-bold tracking-tight">
          VC Insight Engine
        </h1>
        <p className="mb-8 text-lg text-muted-foreground">
          AI-powered value creation analysis for portfolio companies. Upload your
          data, let our engine discover actionable insights, and generate
          executive-ready reports.
        </p>

        <div className="mb-12 grid grid-cols-1 gap-6 sm:grid-cols-3">
          <div className="rounded-lg border bg-card p-6 text-left">
            <FileSpreadsheet className="mb-3 h-8 w-8 text-primary" />
            <h3 className="mb-1 font-semibold">Upload & Profile</h3>
            <p className="text-sm text-muted-foreground">
              Drop your CSV or Excel files and get instant data profiling with
              quality metrics.
            </p>
          </div>
          <div className="rounded-lg border bg-card p-6 text-left">
            <Brain className="mb-3 h-8 w-8 text-accent" />
            <h3 className="mb-1 font-semibold">AI Analysis</h3>
            <p className="text-sm text-muted-foreground">
              Autonomous hypothesis generation, statistical testing, and ML
              modeling with full transparency.
            </p>
          </div>
          <div className="rounded-lg border bg-card p-6 text-left">
            <BarChart3 className="mb-3 h-8 w-8 text-primary" />
            <h3 className="mb-1 font-semibold">Actionable Reports</h3>
            <p className="text-sm text-muted-foreground">
              Executive summaries with SHAP explanations and export to PDF,
              PowerPoint, or CSV.
            </p>
          </div>
        </div>

        <Button
          size="lg"
          className="gap-2 text-base"
          onClick={() => router.push("/sessions/new")}
        >
          Start New Analysis
          <ArrowRight className="h-5 w-5" />
        </Button>
      </div>
    </div>
  );
}
