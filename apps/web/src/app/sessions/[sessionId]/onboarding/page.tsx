"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/session-store";
import { useUpdateSession } from "@/hooks/use-session";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ArrowRight, Loader2 } from "lucide-react";
import { toast } from "sonner";

const INDUSTRIES = [
  "SaaS",
  "Fintech",
  "Healthcare",
  "E-commerce",
  "Manufacturing",
  "Other",
];

export default function OnboardingPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;
  const session = useSessionStore((s) => s.session);
  const updateSession = useUpdateSession(sessionId);

  const [companyName, setCompanyName] = useState(
    session?.company_name || "",
  );
  const [industry, setIndustry] = useState(session?.industry || "");
  const [businessContext, setBusinessContext] = useState(
    session?.business_context || "",
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (!companyName.trim() || !industry) {
      toast.error("Please fill in all required fields");
      return;
    }

    updateSession.mutate(
      {
        company_name: companyName,
        industry,
        business_context: businessContext,
        current_step: "upload",
      },
      {
        onSuccess: () => {
          router.push(`/sessions/${sessionId}/upload`);
        },
        onError: () => {
          toast.error("Failed to save. Please try again.");
        },
      },
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <Card>
        <CardHeader>
          <CardTitle>Company Onboarding</CardTitle>
          <CardDescription>
            Tell us about the portfolio company to tailor the analysis.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="company-name">
                Company Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="company-name"
                placeholder="e.g. Acme Corp"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="industry">
                Industry <span className="text-destructive">*</span>
              </Label>
              <Select value={industry} onValueChange={setIndustry}>
                <SelectTrigger id="industry">
                  <SelectValue placeholder="Select an industry" />
                </SelectTrigger>
                <SelectContent>
                  {INDUSTRIES.map((ind) => (
                    <SelectItem key={ind} value={ind}>
                      {ind}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="context">Business Context</Label>
              <Textarea
                id="context"
                placeholder="Describe the company's business model, key metrics, current challenges, and what you're hoping to learn from this analysis..."
                rows={6}
                value={businessContext}
                onChange={(e) => setBusinessContext(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                The more context you provide, the more tailored the analysis
                will be.
              </p>
            </div>

            <Button
              type="submit"
              className="w-full gap-2"
              disabled={updateSession.isPending}
            >
              {updateSession.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowRight className="h-4 w-4" />
              )}
              Continue to Upload
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
