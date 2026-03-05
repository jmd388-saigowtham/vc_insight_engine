"use client";

import { useParams, useRouter, usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  ClipboardList,
  Upload,
  TableProperties,
  Brain,
  Target,
  BarChart3,
  Lightbulb,
  FlaskConical,
  Cpu,
  Sparkles,
  FileText,
  Check,
  Lock,
} from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const STEPS = [
  { key: "onboarding", label: "Onboarding", icon: ClipboardList },
  { key: "upload", label: "Upload", icon: Upload },
  { key: "profiling", label: "Profiling", icon: TableProperties },
  { key: "workspace", label: "AI Workspace", icon: Brain },
  { key: "target", label: "Target", icon: Target },
  { key: "eda", label: "EDA", icon: BarChart3 },
  { key: "hypotheses", label: "Hypotheses", icon: Lightbulb },
  { key: "hypothesis-results", label: "Results", icon: FlaskConical },
  { key: "models", label: "Models", icon: Cpu },
  { key: "shap", label: "SHAP", icon: Sparkles },
  { key: "report", label: "Report", icon: FileText },
] as const;

export function WizardNav({ currentStep }: { currentStep: string }) {
  const params = useParams();
  const router = useRouter();
  const pathname = usePathname();
  const sessionId = params.sessionId as string;

  const currentIndex = STEPS.findIndex((s) => s.key === currentStep);

  function getStepState(index: number) {
    if (index < currentIndex) return "completed";
    if (index === currentIndex) return "current";
    return "locked";
  }

  function handleClick(step: (typeof STEPS)[number], index: number) {
    const state = getStepState(index);
    if (state === "locked") return;
    router.push(`/sessions/${sessionId}/${step.key}`);
  }

  return (
    <TooltipProvider delayDuration={0}>
      <nav className="border-b bg-card px-4 py-3">
        <div className="mx-auto flex max-w-7xl items-center gap-1 overflow-x-auto">
          {STEPS.map((step, index) => {
            const state = getStepState(index);
            const Icon = step.icon;
            const isActive = pathname.includes(step.key);

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
                        state === "locked" &&
                          "bg-muted text-muted-foreground",
                      )}
                    >
                      {state === "completed" ? (
                        <Check className="h-3 w-3" />
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
      </nav>
    </TooltipProvider>
  );
}
