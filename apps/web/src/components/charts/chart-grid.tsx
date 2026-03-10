"use client";

import { useState } from "react";
import type { Artifact } from "@/types/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Expand } from "lucide-react";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ChartGridProps {
  artifacts: Artifact[];
  loading?: boolean;
}

export function ChartGrid({ artifacts, loading }: ChartGridProps) {
  const [expanded, setExpanded] = useState<Artifact | null>(null);

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="rounded-lg border space-y-3">
            <div className="p-4 pb-0 space-y-1">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
            <div className="px-4 pb-4">
              <Skeleton className="h-48 w-full rounded-md" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (!artifacts || artifacts.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-12 text-center">
        <p className="text-sm text-muted-foreground">
          No visualizations available yet. Run the analysis to generate charts.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {artifacts.map((artifact) => (
          <Card
            key={artifact.id}
            className="group cursor-pointer transition-shadow hover:shadow-md"
            onClick={() => setExpanded(artifact)}
          >
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle className="text-sm">{artifact.title}</CardTitle>
                  {artifact.description && (
                    <CardDescription className="text-xs">
                      {artifact.description}
                    </CardDescription>
                  )}
                </div>
                <Expand className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
            </CardHeader>
            <CardContent>
              {artifact.file_path ? (
                <img
                  src={`${BASE_URL}${artifact.file_path}`}
                  alt={artifact.title}
                  className="w-full rounded-md"
                  loading="lazy"
                />
              ) : (
                <div className="flex h-48 items-center justify-center rounded-md bg-muted">
                  <p className="text-xs text-muted-foreground">No preview</p>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog
        open={expanded !== null}
        onOpenChange={() => setExpanded(null)}
      >
        {expanded && (
          <DialogContent className="max-w-5xl">
            <DialogHeader>
              <DialogTitle>{expanded.title}</DialogTitle>
            </DialogHeader>
            <div className="max-h-[75vh] overflow-auto">
              {expanded.file_path ? (
                <img
                  src={`${BASE_URL}${expanded.file_path}`}
                  alt={expanded.title}
                  className="w-full"
                />
              ) : (
                <div className="flex h-48 items-center justify-center rounded-md bg-muted">
                  <p className="text-xs text-muted-foreground">No preview</p>
                </div>
              )}
            </div>
          </DialogContent>
        )}
      </Dialog>
    </>
  );
}
