"use client";

import { useParams, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  ClipboardList,
  Upload,
  TableProperties,
  Brain,
  Target,
  Filter,
  BarChart3,
  Lightbulb,
  FlaskConical,
  Cpu,
  Sparkles,
  FileText,
  Check,
  Lock,
  Loader2,
  AlertTriangle,
  XCircle,
} from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ThemeToggle } from "@/components/theme-toggle";

const STEPS = [
  { key: "onboarding", label: "Onboarding", icon: ClipboardList },
  { key: "upload", label: "Upload", icon: Upload },
  { key: "profiling", label: "Profiling", icon: TableProperties },
  { key: "workspace", label: "AI Workspace", icon: Brain },
  { key: "target", label: "Target", icon: Target },
  { key: "feature-selection", label: "Features", icon: Filter },
  { key: "eda", label: "EDA", icon: BarChart3 },
  { key: "hypotheses", label: "Hypotheses", icon: Lightbulb },
  { key: "hypothesis-results", label: "Results", icon: FlaskConical },
  { key: "models", label: "Models", icon: Cpu },
  { key: "shap", label: "SHAP", icon: Sparkles },
  { key: "report", label: "Report", icon: FileText },
] as const;

// Map UI step keys to pipeline step keys used in step_states
const STEP_KEY_MAP: Record<string, string> = {
  profiling: "profiling",
  target: "target_id",
  "feature-selection": "feature_selection",
  eda: "eda",
  hypotheses: "hypothesis",
  "hypothesis-results": "hypothesis",
  models: "modeling",
  shap: "explainability",
  report: "report",
};

type StepVisual = "completed" | "current" | "stale" | "failed" | "ready" | "locked";

export function WizardNav({
  currentStep,
  highWaterStep,
  stepStates,
}: {
  currentStep: string;
  highWaterStep: string;
  stepStates?: Record<string, string> | null;
}) {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;

  const highWaterIndex = STEPS.findIndex((s) => s.key === highWaterStep);
  const activeIndex = STEPS.findIndex((s) => s.key === currentStep);

  function getStepState(step: (typeof STEPS)[number], index: number): StepVisual {
    if (stepStates) {
      const pipelineKey = STEP_KEY_MAP[step.key];
      const dbState = pipelineKey ? stepStates[pipelineKey] : undefined;

      if (dbState === "DONE") return "completed";
      if (dbState === "RUNNING") return "current";
      if (dbState === "STALE") return "stale";
      if (dbState === "FAILED") return "failed";
      if (dbState === "READY") return "ready";
      // Steps without pipeline mapping (onboarding, upload, workspace) use high water mark
      if (!pipelineKey) {
        if (index <= highWaterIndex) return index === activeIndex ? "current" : "completed";
        return "locked";
      }
      return "locked";
    }
    // Fallback: original high water mark logic
    if (index <= highWaterIndex) return index === activeIndex ? "current" : "completed";
    return "locked";
  }

  function handleClick(step: (typeof STEPS)[number], index: number) {
    const state = getStepState(step, index);
    if (state === "locked") return;
    router.push(`/sessions/${sessionId}/${step.key}`);
  }

  return (
    <TooltipProvider delayDuration={0}>
      <nav className="border-b bg-card px-4 py-3">
        <div className="mx-auto flex max-w-7xl items-center gap-1 overflow-x-auto">
          <div className="flex flex-1 items-center gap-1 overflow-x-auto">
            {STEPS.map((step, index) => {
              const state = getStepState(step, index);
              const Icon = step.icon;

              return (
                <Tooltip key={step.key}>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => handleClick(step, index)}
                      disabled={state === "locked"}
                      className={cn(
                        "group flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
                        state === "completed" &&
                          "text-accent hover:bg-accent/10 cursor-pointer",
                        state === "current" &&
                          "bg-primary/10 text-primary",
                        state === "ready" &&
                          "text-muted-foreground hover:bg-muted/50 cursor-pointer",
                        state === "stale" &&
                          "text-yellow-600 hover:bg-yellow-50 cursor-pointer dark:text-yellow-400 dark:hover:bg-yellow-950",
                        state === "failed" &&
                          "text-red-600 hover:bg-red-50 cursor-pointer dark:text-red-400 dark:hover:bg-red-950",
                        state === "locked" &&
                          "text-muted-foreground/50 cursor-not-allowed",
                      )}
                    >
                      <span
                        className={cn(
                          "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px]",
                          state === "completed" &&
                            "bg-accent/20 text-accent",
                          state === "current" &&
                            "bg-primary text-primary-foreground",
                          state === "ready" &&
                            "bg-muted text-muted-foreground border border-border",
                          state === "stale" &&
                            "bg-yellow-100 text-yellow-600 dark:bg-yellow-900 dark:text-yellow-400",
                          state === "failed" &&
                            "bg-red-100 text-red-600 dark:bg-red-900 dark:text-red-400",
                          state === "locked" &&
                            "bg-muted text-muted-foreground",
                        )}
                      >
                        {state === "completed" ? (
                          <Check className="h-3 w-3" />
                        ) : state === "current" ? (
                          stepStates ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Icon className="h-3 w-3" />
                          )
                        ) : state === "stale" ? (
                          <AlertTriangle className="h-3 w-3" />
                        ) : state === "failed" ? (
                          <XCircle className="h-3 w-3" />
                        ) : state === "locked" ? (
                          <Lock className="h-3 w-3" />
                        ) : (
                          <Icon className="h-3 w-3" />
                        )}
                      </span>
                      <span className="hidden whitespace-nowrap lg:inline">
                        {step.label}
                      </span>
                      {index < STEPS.length - 1 && (
                        <span
                          className={cn(
                            "ml-1 hidden h-px w-4 sm:block",
                            state === "completed"
                              ? "bg-accent"
                              : state === "stale"
                                ? "bg-yellow-400"
                                : state === "failed"
                                  ? "bg-red-400"
                                  : "bg-border",
                          )}
                        />
                      )}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">
                    <p>
                      {index + 1}. {step.label}
                    </p>
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </div>
          <ThemeToggle />
        </div>
      </nav>
    </TooltipProvider>
  );
}
