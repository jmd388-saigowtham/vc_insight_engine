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
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-72" />
        ))}
      </div>
    );
  }

  if (artifacts.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-muted-foreground">
        No visualizations available yet.
      </p>
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
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
                  <CardDescription className="text-xs">
                    {artifact.description}
                  </CardDescription>
                </div>
                <Expand className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
            </CardHeader>
            <CardContent>
              {artifact.artifact_type === "image" && artifact.file_path && (
                <img
                  src={`${BASE_URL}/artifacts/${artifact.file_path}`}
                  alt={artifact.title}
                  className="w-full rounded-md"
                />
              )}
              {artifact.artifact_type === "html" && artifact.file_path && (
                <iframe
                  src={`${BASE_URL}/artifacts/${artifact.file_path}`}
                  className="h-48 w-full rounded-md border-0"
                  title={artifact.title}
                />
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
              {expanded.artifact_type === "image" && expanded.file_path && (
                <img
                  src={`${BASE_URL}/artifacts/${expanded.file_path}`}
                  alt={expanded.title}
                  className="w-full"
                />
              )}
              {expanded.artifact_type === "html" && expanded.file_path && (
                <iframe
                  src={`${BASE_URL}/artifacts/${expanded.file_path}`}
                  className="h-[70vh] w-full border-0"
                  title={expanded.title}
                />
              )}
            </div>
          </DialogContent>
        )}
      </Dialog>
    </>
  );
}
