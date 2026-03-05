"use client";

import { useParams } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  FileText,
  Download,
  CheckCircle,
  Loader2,
  Presentation,
  Sheet,
} from "lucide-react";
import { toast } from "sonner";
import type { Report } from "@/types/api";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function ReportPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;

  const { data: report, isLoading } = useQuery({
    queryKey: ["report", sessionId],
    queryFn: () =>
      api.get<Report>(`/sessions/${sessionId}/report`),
  });

  const completeAnalysis = useMutation({
    mutationFn: () =>
      api.post(`/sessions/${sessionId}/complete`),
    onSuccess: () => {
      toast.success("Analysis completed successfully!");
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!report) {
    return (
      <Card className="p-12 text-center">
        <Loader2 className="mx-auto mb-4 h-8 w-8 animate-spin text-primary" />
        <p className="text-muted-foreground">
          Generating report... Check the live trace for progress.
        </p>
      </Card>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Analysis Report</h2>
        <p className="text-muted-foreground">
          Executive summary and recommendations from the AI analysis.
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            <CardTitle>Executive Summary</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <p className="whitespace-pre-wrap">{report.executive_summary}</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Key Findings</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3">
            {report.key_findings.map((finding, i) => (
              <li key={i} className="flex items-start gap-2">
                <Badge
                  variant="outline"
                  className="mt-0.5 shrink-0 text-xs"
                >
                  {i + 1}
                </Badge>
                <span className="text-sm">{finding}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recommendations</CardTitle>
          <CardDescription>
            Actionable steps based on the analysis results.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3">
            {report.recommendations.map((rec, i) => (
              <li key={i} className="flex items-start gap-2">
                <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                <span className="text-sm">{rec}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Separator />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Export</CardTitle>
          <CardDescription>
            Download the report in your preferred format.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            {report.export_urls.pdf && (
              <Button
                variant="outline"
                className="gap-2"
                asChild
              >
                <a
                  href={`${BASE_URL}${report.export_urls.pdf}`}
                  download
                >
                  <Download className="h-4 w-4" />
                  PDF Report
                </a>
              </Button>
            )}
            {report.export_urls.pptx && (
              <Button
                variant="outline"
                className="gap-2"
                asChild
              >
                <a
                  href={`${BASE_URL}${report.export_urls.pptx}`}
                  download
                >
                  <Presentation className="h-4 w-4" />
                  PowerPoint
                </a>
              </Button>
            )}
            {report.export_urls.csv && (
              <Button
                variant="outline"
                className="gap-2"
                asChild
              >
                <a
                  href={`${BASE_URL}${report.export_urls.csv}`}
                  download
                >
                  <Sheet className="h-4 w-4" />
                  CSV Data
                </a>
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <Button
        size="lg"
        className="w-full gap-2"
        onClick={() => completeAnalysis.mutate()}
        disabled={completeAnalysis.isPending}
      >
        {completeAnalysis.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <CheckCircle className="h-4 w-4" />
        )}
        Complete Analysis
      </Button>
    </div>
  );
}
