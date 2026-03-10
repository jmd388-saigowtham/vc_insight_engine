"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useTables, useUpdateColumnDescription } from "@/hooks/use-tables";
import { useWizardNavigation } from "@/hooks/use-wizard-navigation";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowRight, Check, Loader2, Pencil } from "lucide-react";
import { toast } from "sonner";
import type { ColumnProfile } from "@/types/api";

function ColumnRow({ col }: { col: ColumnProfile }) {
  const [editing, setEditing] = useState(false);
  const [desc, setDesc] = useState(col.description || "");
  const updateDesc = useUpdateColumnDescription();

  function handleSave() {
    updateDesc.mutate(
      { columnId: col.id, description: desc },
      {
        onSuccess: () => {
          setEditing(false);
          toast.success("Description saved");
        },
      },
    );
  }

  return (
    <tr className="border-b text-sm">
      <td className="px-3 py-2 font-medium">{col.column_name}</td>
      <td className="px-3 py-2">
        <Badge variant="outline" className="text-xs">
          {col.dtype}
        </Badge>
      </td>
      <td className="px-3 py-2 text-right">
        {col.null_pct != null ? col.null_pct.toFixed(1) : "0"}%
      </td>
      <td className="px-3 py-2 text-right">
        {col.unique_count != null ? col.unique_count.toLocaleString() : "-"}
      </td>
      <td className="px-3 py-2">{col.min_value ?? "-"}</td>
      <td className="px-3 py-2">{col.max_value ?? "-"}</td>
      <td className="px-3 py-2">
        {col.mean_value != null ? col.mean_value.toFixed(2) : "-"}
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">
        {(col.sample_values ?? []).slice(0, 3).map(String).join(", ")}
      </td>
      <td className="px-3 py-2">
        {editing ? (
          <div className="flex items-center gap-1">
            <Input
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              className="h-7 text-xs"
              placeholder="Describe this column..."
            />
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7"
              onClick={handleSave}
              disabled={updateDesc.isPending}
            >
              <Check className="h-3 w-3" />
            </Button>
          </div>
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            {col.description || "Add description"}
            <Pencil className="h-3 w-3" />
          </button>
        )}
      </td>
    </tr>
  );
}

export default function ProfilingPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const { data: tables, isLoading } = useTables(sessionId);
  const { navigateToNext, isPending } = useWizardNavigation("profiling");

  function handleStart() {
    navigateToNext("workspace");
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!tables || tables.length === 0) {
    return (
      <p className="text-center text-muted-foreground">
        No data files found. Please upload files first.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Data Profiling</h2>
        <p className="text-muted-foreground">
          Review column statistics and add descriptions to guide the AI
          analysis.
        </p>
      </div>

      <Tabs defaultValue={tables[0].file_id}>
        <TabsList>
          {tables.map((t) => (
            <TabsTrigger key={t.file_id} value={t.file_id}>
              {t.filename}
            </TabsTrigger>
          ))}
        </TabsList>

        {tables.map((t) => (
          <TabsContent key={t.file_id} value={t.file_id}>
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">{t.filename}</CardTitle>
                <CardDescription>
                  {t.row_count?.toLocaleString()} rows,{" "}
                  {t.column_count} columns
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b text-xs font-medium text-muted-foreground">
                        <th className="px-3 py-2">Column</th>
                        <th className="px-3 py-2">Type</th>
                        <th className="px-3 py-2 text-right">Null %</th>
                        <th className="px-3 py-2 text-right">Unique</th>
                        <th className="px-3 py-2">Min</th>
                        <th className="px-3 py-2">Max</th>
                        <th className="px-3 py-2">Mean</th>
                        <th className="px-3 py-2">Samples</th>
                        <th className="px-3 py-2">Description</th>
                      </tr>
                    </thead>
                    <tbody>
                      {t.columns.map((col) => (
                        <ColumnRow key={col.id} col={col} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>

      <Button
        className="gap-2"
        size="lg"
        onClick={handleStart}
        disabled={isPending}
      >
        {isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <ArrowRight className="h-4 w-4" />
        )}
        Start AI Analysis
      </Button>
    </div>
  );
}
