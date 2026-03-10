"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useWizardNavigation } from "@/hooks/use-wizard-navigation";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ArrowRight,
  ChevronDown,
  CheckCircle,
  XCircle,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Hypothesis } from "@/types/api";

export default function HypothesisResultsPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const { navigateToNext, isPending } = useWizardNavigation("hypothesis-results");

  const { data: hypotheses, isLoading } = useQuery({
    queryKey: ["hypothesis-results", sessionId],
    queryFn: () =>
      api.get<Hypothesis[]>(`/sessions/${sessionId}/hypotheses?with_results=true`),
  });

  const testedHypotheses =
    hypotheses?.filter((h) => h.result !== null) ?? [];

  function handleContinue() {
    navigateToNext("models");
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Hypothesis Results</h2>
        <p className="text-muted-foreground">
          Statistical test results for each approved hypothesis.
        </p>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b text-xs font-medium text-muted-foreground">
                  <th className="px-4 py-3">Hypothesis</th>
                  <th className="px-4 py-3">Test Statistic</th>
                  <th className="px-4 py-3">p-value</th>
                  <th className="px-4 py-3">Conclusion</th>
                  <th className="px-4 py-3 w-10"></th>
                </tr>
              </thead>
              <tbody>
                {testedHypotheses.map((hyp) => (
                  <HypothesisRow key={hyp.id} hypothesis={hyp} />
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {testedHypotheses.length === 0 && (
        <Card className="p-12 text-center">
          <Loader2 className="mx-auto mb-4 h-8 w-8 animate-spin text-primary" />
          <p className="text-muted-foreground">
            Running hypothesis tests... Check the live trace for progress.
          </p>
        </Card>
      )}

      {testedHypotheses.length > 0 && (
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
          Continue to Models
        </Button>
      )}
    </div>
  );
}

function HypothesisRow({ hypothesis }: { hypothesis: Hypothesis }) {
  const [open, setOpen] = useState(false);
  const r = hypothesis.result!;
  const supported = r.supported;

  return (
    <>
      <tr
        className="cursor-pointer border-b hover:bg-muted/50"
        onClick={() => setOpen((o) => !o)}
      >
        <td className="px-4 py-3 max-w-xs">
          <div className="flex items-center gap-2">
            {supported ? (
              <CheckCircle className="h-4 w-4 shrink-0 text-green-500" />
            ) : (
              <XCircle className="h-4 w-4 shrink-0 text-red-500" />
            )}
            <span className="truncate">{hypothesis.statement}</span>
          </div>
        </td>
        <td className="px-4 py-3 font-mono text-xs">
          {r.test_statistic.toFixed(4)}
        </td>
        <td className="px-4 py-3">
          <Badge
            variant={r.p_value < 0.05 ? "default" : "secondary"}
            className="font-mono text-xs"
          >
            {r.p_value.toFixed(6)}
          </Badge>
        </td>
        <td className="px-4 py-3">
          <Badge
            variant={supported ? "default" : "destructive"}
            className={cn(
              "text-xs",
              supported && "bg-green-500/10 text-green-700",
            )}
          >
            {supported ? "Supported" : "Rejected"}
          </Badge>
        </td>
        <td className="px-4 py-3">
          <ChevronDown
            className={cn(
              "h-4 w-4 text-muted-foreground transition-transform",
              open && "rotate-180",
            )}
          />
        </td>
      </tr>
      {open && (
        <tr className="border-b bg-muted/30">
          <td colSpan={5} className="px-4 py-3 text-sm">
            {r.conclusion}
          </td>
        </tr>
      )}
    </>
  );
}
