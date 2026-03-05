"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useUpdateSession } from "@/hooks/use-session";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
  TrendingDown,
  TrendingUp,
  RefreshCw,
  ShoppingCart,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";

interface Opportunity {
  id: string;
  title: string;
  description: string;
  type: "churn" | "expansion" | "cross_sell" | "upsell";
  confidence: number;
  key_metrics: string[];
}

const TYPE_CONFIG = {
  churn: {
    icon: TrendingDown,
    color: "text-red-500",
    bg: "bg-red-500/10",
  },
  expansion: {
    icon: TrendingUp,
    color: "text-green-500",
    bg: "bg-green-500/10",
  },
  cross_sell: {
    icon: ShoppingCart,
    color: "text-blue-500",
    bg: "bg-blue-500/10",
  },
  upsell: {
    icon: RefreshCw,
    color: "text-purple-500",
    bg: "bg-purple-500/10",
  },
};

export default function WorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;
  const updateSession = useUpdateSession(sessionId);

  const { data: opportunities, isLoading } = useQuery({
    queryKey: ["opportunities", sessionId],
    queryFn: () =>
      api.get<Opportunity[]>(`/sessions/${sessionId}/opportunities`),
  });

  function handleSelect(opportunity: Opportunity) {
    updateSession.mutate(
      { current_step: "target" },
      {
        onSuccess: () => {
          toast.success(`Selected: ${opportunity.title}`);
          router.push(`/sessions/${sessionId}/target`);
        },
      },
    );
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-48" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">AI Workspace</h2>
        <p className="text-muted-foreground">
          Based on your data, the AI has identified these value creation
          opportunities. Select one to begin the analysis.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {(opportunities ?? []).map((opp) => {
          const config = TYPE_CONFIG[opp.type];
          const Icon = config.icon;

          return (
            <Card
              key={opp.id}
              className="cursor-pointer transition-all hover:shadow-md hover:ring-1 hover:ring-primary/20"
              onClick={() => handleSelect(opp)}
            >
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <div className={`rounded-lg p-2 ${config.bg}`}>
                    <Icon className={`h-5 w-5 ${config.color}`} />
                  </div>
                  <div>
                    <CardTitle className="text-base">{opp.title}</CardTitle>
                    <Badge variant="outline" className="mt-1 text-xs">
                      {opp.type.replace("_", " ")}
                    </Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <CardDescription>{opp.description}</CardDescription>

                <div className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Confidence</span>
                    <span className="font-medium">
                      {(opp.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <Progress value={opp.confidence * 100} className="h-1.5" />
                </div>

                <div className="flex flex-wrap gap-1">
                  {opp.key_metrics.map((metric) => (
                    <Badge
                      key={metric}
                      variant="secondary"
                      className="text-xs"
                    >
                      {metric}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {(!opportunities || opportunities.length === 0) && (
        <Card className="p-12 text-center">
          <Loader2 className="mx-auto mb-4 h-8 w-8 animate-spin text-primary" />
          <p className="text-muted-foreground">
            AI is analyzing your data... Check the live trace for progress.
          </p>
        </Card>
      )}
    </div>
  );
}
