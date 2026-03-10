"use client";

import { useState, useMemo, useEffect } from "react";
import { useParams } from "next/navigation";
import { useFeatureSelection, useUpdateFeatureSelection } from "@/hooks/use-feature-selection";
import { useWizardNavigation } from "@/hooks/use-wizard-navigation";
import { useStepStates } from "@/hooks/use-step-states";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { StepStatusBanner } from "@/components/step-status-banner";
import { ArrowRight, Target, Filter, Loader2, Search, Save, AlertTriangle, Brain, CheckCircle2, ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import { PendingProposals } from "@/components/proposal/pending-proposals";

export default function FeatureSelectionPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const { navigateToNext, isPending: isNavPending } = useWizardNavigation("feature-selection");
  const { data: stepStates } = useStepStates(sessionId);
  const featureSelState = stepStates?.feature_selection;

  const { data, isLoading } = useFeatureSelection(sessionId);
  const updateMutation = useUpdateFeatureSelection(sessionId);

  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [initialized, setInitialized] = useState(false);
  const [search, setSearch] = useState("");
  const [expandedFeature, setExpandedFeature] = useState<string | null>(null);

  // Initialize selection state from server data once
  useEffect(() => {
    if (data && !initialized) {
      const initial: Record<string, boolean> = {};
      for (const feat of data.features) {
        initial[feat.name] = feat.selected;
      }
      setSelected(initial);
      setInitialized(true);
    }
  }, [data, initialized]);

  const filteredFeatures = useMemo(() => {
    if (!data) return [];
    const q = search.toLowerCase();
    return data.features.filter(
      (f) => f.name.toLowerCase().includes(q) || f.dtype.toLowerCase().includes(q)
    );
  }, [data, search]);

  const selectedCount = Object.values(selected).filter(Boolean).length;
  const totalCount = data?.features.length ?? 0;

  function toggleFeature(name: string) {
    setSelected((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  function selectAll() {
    const next: Record<string, boolean> = {};
    for (const feat of data?.features ?? []) {
      next[feat.name] = true;
    }
    setSelected(next);
  }

  function deselectAll() {
    const next: Record<string, boolean> = {};
    for (const feat of data?.features ?? []) {
      next[feat.name] = false;
    }
    setSelected(next);
  }

  function handleSave() {
    if (!data) return;
    const selectedFeatures = data.features
      .filter((f) => selected[f.name])
      .map((f) => f.name);
    updateMutation.mutate({
      target_column: data.target_column,
      selected_features: selectedFeatures,
    });
  }

  function handleContinue() {
    if (!data) return;
    const selectedFeatures = data.features
      .filter((f) => selected[f.name])
      .map((f) => f.name);
    updateMutation.mutate(
      {
        target_column: data.target_column,
        selected_features: selectedFeatures,
      },
      { onSuccess: () => navigateToNext("eda") }
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Feature Selection</h2>
        <p className="text-muted-foreground">
          Choose which features to include in the analysis pipeline.
        </p>
      </div>

      <PendingProposals sessionId={sessionId} step="feature_selection" />

      <StepStatusBanner state={featureSelState} stepLabel="Feature Selection" />

      {data && !data.target_column && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="py-4 flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            <p className="text-sm">No target column set — complete the Target step first before selecting features.</p>
          </CardContent>
        </Card>
      )}

      {data && (
        <>
          <Card>
            <CardHeader>
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-primary/10 p-2">
                  <Target className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <CardTitle className="text-base">
                    Target: {data.target_column}
                  </CardTitle>
                  <CardDescription>
                    This variable will be predicted. Features below are the inputs.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-primary/10 p-2">
                    <Filter className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <CardTitle className="text-base">Features</CardTitle>
                    <CardDescription>
                      {selectedCount} of {totalCount} features selected
                    </CardDescription>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={selectAll}>
                    Select All
                  </Button>
                  <Button variant="outline" size="sm" onClick={deselectAll}>
                    Deselect All
                  </Button>
                </div>
              </div>
              <div className="relative mt-3">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search features..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-9"
                />
              </div>
            </CardHeader>
            <CardContent>
              {selectedCount === 0 && (
                <p className="mb-3 text-sm text-destructive">
                  At least one feature must be selected to continue.
                </p>
              )}
              <div className="space-y-2">
                {filteredFeatures.map((feat) => {
                  const isExpanded = expandedFeature === feat.name;
                  const hasAgentData = feat.source === "agent";
                  return (
                    <div
                      key={feat.name}
                      className="rounded-md border px-3 py-2"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <Switch
                            checked={selected[feat.name] ?? feat.selected}
                            onCheckedChange={() => toggleFeature(feat.name)}
                          />
                          <Label className="cursor-pointer">{feat.name}</Label>
                          <Badge variant="outline" className="text-xs">
                            {feat.dtype}
                          </Badge>
                          {feat.leakage_risk && (
                            <Badge variant="destructive" className="gap-1 text-xs">
                              <AlertTriangle className="h-3 w-3" />
                              Leakage Risk
                            </Badge>
                          )}
                          {hasAgentData ? (
                            <Badge variant="secondary" className="gap-1 text-[10px]">
                              <Sparkles className="h-2.5 w-2.5" />
                              AI analyzed
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-[10px] text-muted-foreground">
                              Not yet analyzed
                            </Badge>
                          )}
                        </div>
                        <div className="flex items-center gap-3">
                          {feat.null_pct > 0 && (
                            <span className="text-xs text-muted-foreground">
                              {feat.null_pct.toFixed(1)}% null
                            </span>
                          )}
                          <div className="flex items-center gap-1.5">
                            <div className="h-2 w-20 overflow-hidden rounded-full bg-muted">
                              <div
                                className="h-full rounded-full bg-primary transition-all"
                                style={{ width: `${Math.min(feat.importance * 100, 100)}%` }}
                              />
                            </div>
                            <span className="text-xs text-muted-foreground w-8">
                              {(feat.importance * 100).toFixed(0)}%
                            </span>
                          </div>
                          {(feat.reasoning || feat.leakage_risk) && (
                            <button
                              onClick={() => setExpandedFeature(isExpanded ? null : feat.name)}
                              className="p-0.5 rounded hover:bg-muted"
                            >
                              {isExpanded ? (
                                <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                              ) : (
                                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                              )}
                            </button>
                          )}
                        </div>
                      </div>
                      {isExpanded && (
                        <div className="mt-2 ml-10 space-y-1.5 rounded-md bg-muted/50 p-2">
                          {feat.reasoning && (
                            <div className="flex items-start gap-1.5 text-xs text-muted-foreground">
                              <Brain className="mt-0.5 h-3 w-3 shrink-0 text-primary" />
                              <span>{feat.reasoning}</span>
                            </div>
                          )}
                          {feat.leakage_risk && (
                            <div className="flex items-start gap-1.5 text-xs text-destructive">
                              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                              <span>
                                This feature has high correlation with the target and may cause data leakage.
                                Consider excluding it for more reliable model performance.
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                      {!isExpanded && feat.reasoning && (
                        <div className="mt-1.5 ml-10 flex items-start gap-1.5 text-xs text-muted-foreground">
                          <Brain className="mt-0.5 h-3 w-3 shrink-0" />
                          <span className="truncate">{feat.reasoning}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
                {filteredFeatures.length === 0 && (
                  <p className="py-4 text-center text-sm text-muted-foreground">
                    No features match your search.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          {selectedCount > 0 && (
            <Card className="border-primary/20 bg-primary/5">
              <CardContent className="py-4">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="h-5 w-5 text-primary" />
                  <div>
                    <p className="text-sm font-medium">
                      {selectedCount} of {totalCount} features selected for analysis
                    </p>
                    {data?.features.some((f) => f.leakage_risk && selected[f.name]) && (
                      <p className="mt-1 flex items-center gap-1 text-xs text-destructive">
                        <AlertTriangle className="h-3 w-3" />
                        Warning: selection includes features flagged for potential leakage
                      </p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              className="gap-2"
              onClick={handleSave}
              disabled={updateMutation.isPending || selectedCount === 0}
            >
              {updateMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Save Selection
            </Button>
            <Button
              className="gap-2"
              size="lg"
              onClick={handleContinue}
              disabled={isNavPending || updateMutation.isPending || selectedCount === 0}
            >
              {isNavPending || updateMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowRight className="h-4 w-4" />
              )}
              Continue to EDA
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
