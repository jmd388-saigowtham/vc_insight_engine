"use client";

import { Badge } from "@/components/ui/badge";
import { Eraser, Tag } from "lucide-react";

interface PreprocessingViewProps {
  plan: Record<string, unknown>;
}

export function PreprocessingView({ plan }: PreprocessingViewProps) {
  const missing = plan.missing_strategy as Record<string, unknown> | undefined;
  const encoding = plan.encoding as Record<string, unknown> | undefined;
  const missingOverrides = missing?.column_overrides as Record<string, unknown> | undefined;
  const encodingOverrides = encoding?.column_overrides as Record<string, unknown> | undefined;

  return (
    <div className="space-y-3">
      {missing && (
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm">
            <Eraser className="h-4 w-4 text-amber-500" />
            <span className="font-medium">Missing Values</span>
          </div>
          <div className="ml-6 space-y-0.5 text-xs text-muted-foreground">
            <p>
              Numeric: <Badge variant="outline" className="text-[10px]">{(missing.numeric_default as string) ?? "median"}</Badge>
              {" "}Categorical: <Badge variant="outline" className="text-[10px]">{(missing.categorical_default as string) ?? "mode"}</Badge>
            </p>
            {missing.drop_high_null_threshold !== undefined && (
              <p>Drop columns with &gt;{Math.round((missing.drop_high_null_threshold as number) * 100)}% null</p>
            )}
            {missingOverrides && Object.keys(missingOverrides).length > 0 && (
              <p>Custom overrides for {Object.keys(missingOverrides).length} column(s)</p>
            )}
          </div>
        </div>
      )}

      {encoding && (
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm">
            <Tag className="h-4 w-4 text-blue-500" />
            <span className="font-medium">Encoding</span>
          </div>
          <div className="ml-6 text-xs text-muted-foreground">
            <p>
              Method: <Badge variant="outline" className="text-[10px]">{(encoding.method as string) ?? "label"}</Badge>
            </p>
            {encodingOverrides && Object.keys(encodingOverrides).length > 0 && (
              <p>Custom encoding for {Object.keys(encodingOverrides).length} column(s)</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
