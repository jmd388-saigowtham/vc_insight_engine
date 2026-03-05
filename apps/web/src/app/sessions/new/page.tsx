"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useCreateSession } from "@/hooks/use-session";
import { useSessionStore } from "@/stores/session-store";
import { Loader2 } from "lucide-react";

export default function NewSessionPage() {
  const router = useRouter();
  const createSession = useCreateSession();
  const setSession = useSessionStore((s) => s.setSession);

  useEffect(() => {
    if (createSession.isPending || createSession.isSuccess) return;

    createSession.mutate(
      {
        company_name: "",
        industry: "",
        business_context: "",
      },
      {
        onSuccess: (session) => {
          setSession(session);
          router.replace(`/sessions/${session.id}/onboarding`);
        },
      },
    );
  }, [createSession, router, setSession]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-muted-foreground">Creating new session...</p>
      </div>
    </div>
  );
}
