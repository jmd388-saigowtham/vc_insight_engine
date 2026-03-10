"use client";

import { useEffect } from "react";
import { useParams, usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { useSession } from "@/hooks/use-session";
import { useSessionStore } from "@/stores/session-store";
import { WizardLayout } from "@/components/wizard/wizard-layout";
import { LiveTraceSidebar } from "@/components/live-trace/live-trace-sidebar";
import { CodeApprovalModal } from "@/components/code-modal/code-approval-modal";
import { ProposalModal } from "@/components/proposal/proposal-modal";
import { FeedbackInput } from "@/components/feedback/feedback-input";
import { ErrorBoundary } from "@/components/error-boundary";
import { useEventStream } from "@/hooks/use-events";
import { Loader2 } from "lucide-react";

const STEPS_WITH_TRACE = [
  "workspace",
  "target",
  "feature-selection",
  "eda",
  "hypotheses",
  "hypothesis-results",
  "models",
  "shap",
  "report",
];

function getCurrentStep(pathname: string): string {
  const segments = pathname.split("/");
  return segments[segments.length - 1] || "onboarding";
}

export default function SessionLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const params = useParams();
  const pathname = usePathname();
  const sessionId = params.sessionId as string;
  const { data: session, isLoading } = useSession(sessionId);
  const setSession = useSessionStore((s) => s.setSession);

  const currentStep = getCurrentStep(pathname);
  const showTrace = STEPS_WITH_TRACE.includes(currentStep);

  useEventStream(showTrace ? sessionId : null);

  useEffect(() => {
    if (session) setSession(session);
  }, [session, setSession]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <>
      <WizardLayout
        currentStep={currentStep}
        highWaterStep={session?.current_step ?? currentStep}
        stepStates={session?.step_states}
        sidebar={showTrace ? <LiveTraceSidebar /> : undefined}
      >
        <ErrorBoundary>
          <AnimatePresence mode="wait">
            <motion.div
              key={pathname}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </ErrorBoundary>
      </WizardLayout>
      <CodeApprovalModal />
      <ProposalModal />
      {showTrace && <FeedbackInput />}
    </>
  );
}
