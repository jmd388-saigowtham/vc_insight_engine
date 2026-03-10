"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowRight, BarChart3, Brain, Building2, Clock, FileSpreadsheet } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { useSessions } from "@/hooks/use-session";

const statusStyles: Record<string, string> = {
  active: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  completed: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  failed: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

export default function HomePage() {
  const router = useRouter();
  const { data: sessions } = useSessions();

  const hasSessions = sessions && sessions.length > 0;

  return (
    <div className="flex min-h-screen flex-col items-center bg-gradient-to-br from-background via-background to-primary/5">
      <div className="mx-auto max-w-3xl px-4 pt-24 text-center">
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

        {hasSessions && (
          <p className="mt-4 text-sm text-muted-foreground">
            or continue an existing analysis
          </p>
        )}
      </div>

      {hasSessions && (
        <div className="mx-auto w-full max-w-5xl px-4 pb-16 pt-12">
          <h2 className="mb-6 text-2xl font-semibold tracking-tight">
            Recent Analyses
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sessions.map((session) => (
              <Card
                key={session.id}
                className="cursor-pointer transition-shadow hover:shadow-md"
                onClick={() =>
                  router.push(
                    `/sessions/${session.id}/${session.current_step}` as never,
                  )
                }
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base">
                      {session.company_name}
                    </CardTitle>
                    <Badge
                      variant="outline"
                      className={statusStyles[session.status] ?? ""}
                    >
                      {session.status}
                    </Badge>
                  </div>
                  <CardDescription className="flex items-center gap-1">
                    <Building2 className="h-3 w-3" />
                    {session.industry}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <span className="capitalize">
                      {session.current_step.replace(/[-_]/g, " ")}
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatDistanceToNow(new Date(session.created_at), {
                        addSuffix: true,
                      })}
                    </span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
