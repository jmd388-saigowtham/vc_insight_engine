import { useParams, useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/session-store";
import { useUpdateSession } from "@/hooks/use-session";
import type { Session } from "@/types/session";

const STEP_ORDER = [
  "onboarding", "upload", "profiling", "workspace", "target",
  "feature-selection", "eda", "hypotheses", "hypothesis-results", "models", "shap", "report",
];

const PROPOSAL_GATED_STEPS = new Set([
  "workspace", "target", "eda", "hypotheses", "models",
]);

export function useWizardNavigation(currentUrlStep: string) {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;
  const session = useSessionStore((s) => s.session);
  const updateSession = useUpdateSession(sessionId);

  const currentUrlIndex = STEP_ORDER.indexOf(currentUrlStep);
  const highWaterIndex = STEP_ORDER.indexOf(session?.current_step ?? "onboarding");
  const isAtFrontier = currentUrlIndex >= highWaterIndex;

  function navigateToNext(nextStep: string, extraData?: Partial<Session>) {
    const isGated = PROPOSAL_GATED_STEPS.has(currentUrlStep);

    if (isAtFrontier && !isGated) {
      // Non-gated step at frontier: advance current_step in DB
      updateSession.mutate(
        { ...extraData, current_step: nextStep },
        { onSuccess: () => router.push(`/sessions/${sessionId}/${nextStep}` as never) }
      );
    } else if (extraData && Object.keys(extraData).length > 0) {
      // Has extra data to persist (e.g., target_column), but don't advance step
      updateSession.mutate(extraData, {
        onSuccess: () => router.push(`/sessions/${sessionId}/${nextStep}` as never),
      });
    } else {
      // Just navigate — no DB mutation needed
      router.push(`/sessions/${sessionId}/${nextStep}` as never);
    }
  }

  return { navigateToNext, isAtFrontier, isPending: updateSession.isPending };
}
