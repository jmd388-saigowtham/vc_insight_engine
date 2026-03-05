"use client";

import { useState } from "react";
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
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { ArrowRight, Target, Loader2 } from "lucide-react";
import { toast } from "sonner";

interface TargetConfig {
  target_variable: string;
  features: { name: string; included: boolean; importance: number }[];
  preview: Record<string, unknown>[];
}

export default function TargetPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;
  const updateSession = useUpdateSession(sessionId);

  const { data: config, isLoading } = useQuery({
    queryKey: ["target", sessionId],
    queryFn: () =>
      api.get<TargetConfig>(`/sessions/${sessionId}/target`),
  });

  const [features, setFeatures] = useState<
    Record<string, boolean>
  >({});

  function toggleFeature(name: string) {
    setFeatures((prev) => ({
      ...prev,
      [name]: prev[name] !== undefined ? !prev[name] : false,
    }));
  }

  function isIncluded(feat: { name: string; included: boolean }) {
    return features[feat.name] !== undefined
      ? features[feat.name]
      : feat.included;
  }

  function handleConfirm() {
    updateSession.mutate(
      { current_step: "eda" },
      {
        onSuccess: () => {
          toast.success("Target confirmed");
          router.push(`/sessions/${sessionId}/eda`);
        },
      },
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Target Variable</h2>
        <p className="text-muted-foreground">
          Review the identified target and select features to include.
        </p>
      </div>

      {config && (
        <>
          <Card>
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-primary/10 p-2">
                  <Target className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <CardTitle className="text-base">
                    Target: {config.target_variable}
                  </CardTitle>
                  <CardDescription>
                    This variable will be predicted by the models.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Feature Selection</CardTitle>
              <CardDescription>
                Toggle features to include or exclude from the analysis.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {config.features.map((feat) => (
                  <div
                    key={feat.name}
                    className="flex items-center justify-between rounded-md border px-3 py-2"
                  >
                    <div className="flex items-center gap-3">
                      <Switch
                        checked={isIncluded(feat)}
                        onCheckedChange={() => toggleFeature(feat.name)}
                      />
                      <Label className="cursor-pointer">{feat.name}</Label>
                    </div>
                    <Badge variant="secondary" className="text-xs">
                      importance: {(feat.importance * 100).toFixed(0)}%
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {config.preview.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Data Preview</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b text-xs text-muted-foreground">
                        {Object.keys(config.preview[0]).map((key) => (
                          <th key={key} className="px-2 py-1.5">
                            {key}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {config.preview.slice(0, 5).map((row, i) => (
                        <tr key={i} className="border-b">
                          {Object.values(row).map((val, j) => (
                            <td key={j} className="px-2 py-1.5 text-xs">
                              {String(val)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          <Button
            className="gap-2"
            size="lg"
            onClick={handleConfirm}
            disabled={updateSession.isPending}
          >
            {updateSession.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ArrowRight className="h-4 w-4" />
            )}
            Confirm Target
          </Button>
        </>
      )}
    </div>
  );
}
