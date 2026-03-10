"use client";

import { Loader2, AlertTriangle, Clock, XCircle, CheckCircle2, Hourglass } from "lucide-react";
import { cn } from "@/lib/utils";

interface StepStatusBannerProps {
  state: string | undefined;
  stepLabel?: string;
  showCompleted?: boolean;
  hasPendingProposal?: boolean;
}

const STATUS_CONFIG: Record<
  string,
  {
    icon: typeof Loader2;
    message: string;
    border: string;
    bg: string;
    text: string;
    iconColor: string;
    animate?: boolean;
  }
> = {
  RUNNING: {
    icon: Loader2,
    message: "AI is working on this step...",
    border: "border-blue-300 dark:border-blue-700",
    bg: "bg-blue-50 dark:bg-blue-950",
    text: "text-blue-800 dark:text-blue-200",
    iconColor: "text-blue-600 dark:text-blue-400",
    animate: true,
  },
  STALE: {
    icon: AlertTriangle,
    message: "Results are stale — upstream data has changed. Re-run to update.",
    border: "border-yellow-300 dark:border-yellow-700",
    bg: "bg-yellow-50 dark:bg-yellow-950",
    text: "text-yellow-800 dark:text-yellow-200",
    iconColor: "text-yellow-600 dark:text-yellow-400",
  },
  READY: {
    icon: Clock,
    message: "Waiting for AI to process this step...",
    border: "border-gray-300 dark:border-gray-700",
    bg: "bg-gray-50 dark:bg-gray-900",
    text: "text-gray-700 dark:text-gray-300",
    iconColor: "text-gray-500 dark:text-gray-400",
  },
  FAILED: {
    icon: XCircle,
    message: "This step encountered an error. Check the live trace for details.",
    border: "border-red-300 dark:border-red-700",
    bg: "bg-red-50 dark:bg-red-950",
    text: "text-red-800 dark:text-red-200",
    iconColor: "text-red-600 dark:text-red-400",
  },
  DONE: {
    icon: CheckCircle2,
    message: "Step completed successfully.",
    border: "border-green-300 dark:border-green-700",
    bg: "bg-green-50 dark:bg-green-950",
    text: "text-green-800 dark:text-green-200",
    iconColor: "text-green-600 dark:text-green-400",
  },
  AWAITING_APPROVAL: {
    icon: Hourglass,
    message: "Awaiting your approval before proceeding.",
    border: "border-amber-300 dark:border-amber-700",
    bg: "bg-amber-50 dark:bg-amber-950",
    text: "text-amber-800 dark:text-amber-200",
    iconColor: "text-amber-600 dark:text-amber-400",
  },
};

export function StepStatusBanner({ state, stepLabel, showCompleted, hasPendingProposal }: StepStatusBannerProps) {
  // Show AWAITING_APPROVAL variant when proposal is pending
  const effectiveState = hasPendingProposal ? "AWAITING_APPROVAL" : state;

  if (!effectiveState || effectiveState === "NOT_STARTED") {
    return null;
  }

  // Only show DONE banner if explicitly requested
  if (effectiveState === "DONE" && !showCompleted) {
    return null;
  }

  const config = STATUS_CONFIG[effectiveState];
  if (!config) return null;

  const Icon = config.icon;
  const label = stepLabel ? `${stepLabel}: ` : "";

  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-lg border p-4",
        config.border,
        config.bg,
      )}
    >
      <Icon
        className={cn(
          "h-5 w-5 shrink-0",
          config.iconColor,
          config.animate && "animate-spin",
        )}
      />
      <p className={cn("text-sm font-medium", config.text)}>
        {label}{config.message}
      </p>
    </div>
  );
}
