"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useFiles, useUploadFile, useListSheets } from "@/hooks/use-tables";
import { useWizardNavigation } from "@/hooks/use-wizard-navigation";
import { Dropzone } from "@/components/upload/dropzone";
import { FileList } from "@/components/upload/file-list";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ArrowRight, Loader2, FileSpreadsheet } from "lucide-react";
import { toast } from "sonner";

export default function UploadPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const { data: files = [], isLoading } = useFiles(sessionId);
  const uploadFile = useUploadFile(sessionId);
  const { navigateToNext, isPending } = useWizardNavigation("upload");

  // Track the latest uploaded xlsx file for sheet selection
  const xlsxFiles = files.filter(
    (f) => f.filename.endsWith(".xlsx") || f.filename.endsWith(".xls"),
  );
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const activeXlsx = selectedFileId
    ? xlsxFiles.find((f) => f.id === selectedFileId) ?? null
    : xlsxFiles.length > 0
      ? xlsxFiles[xlsxFiles.length - 1]
      : null;

  const { data: sheetsData } = useListSheets(activeXlsx?.id ?? null);

  async function handleUpload(file: File, onProgress: (pct: number) => void) {
    try {
      await uploadFile.mutateAsync({ file, onProgress });
      toast.success(`${file.name} uploaded successfully`);
    } catch {
      toast.error(`Failed to upload ${file.name}`);
      throw new Error("Upload failed");
    }
  }

  function handleContinue() {
    navigateToNext("profiling");
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Upload Data Files</CardTitle>
          <CardDescription>
            Upload CSV or XLSX files containing the data you want to analyze.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <Dropzone onUpload={handleUpload} />

          <div>
            <h3 className="mb-3 text-sm font-medium">Uploaded Files</h3>
            <FileList files={files} loading={isLoading} />
          </div>

          {/* Sheet selection for multi-sheet xlsx */}
          {sheetsData?.is_multi_sheet && activeXlsx && (
            <Card className="border-blue-500/30 bg-blue-500/5">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <FileSpreadsheet className="mt-0.5 h-5 w-5 shrink-0 text-blue-500" />
                  <div className="flex-1 space-y-2">
                    <p className="text-sm font-medium">
                      Multiple Sheets Detected
                    </p>
                    <p className="text-xs text-muted-foreground">
                      <strong>{activeXlsx.filename}</strong> contains{" "}
                      {sheetsData.sheets.length} sheets. The first sheet will be
                      used by default.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {sheetsData.sheets.map((sheet) => (
                        <Badge
                          key={sheet.index}
                          variant={sheet.index === 0 ? "default" : "secondary"}
                          className="text-xs"
                        >
                          {sheet.name}
                          {sheet.index === 0 && (
                            <span className="ml-1 text-[10px] opacity-70">(active)</span>
                          )}
                        </Badge>
                      ))}
                    </div>
                    <p className="text-[10px] text-muted-foreground mt-1">
                      All sheets are available for profiling in the next step.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Multi-xlsx selector */}
          {xlsxFiles.length > 1 && (
            <div className="flex flex-wrap gap-2">
              <span className="text-xs text-muted-foreground self-center mr-1">
                View sheets for:
              </span>
              {xlsxFiles.map((f) => (
                <Button
                  key={f.id}
                  variant={activeXlsx?.id === f.id ? "default" : "outline"}
                  size="sm"
                  className="text-xs h-7"
                  onClick={() => setSelectedFileId(f.id)}
                >
                  {f.filename}
                </Button>
              ))}
            </div>
          )}

          {files.length > 0 && (
            <Button
              className="w-full gap-2"
              onClick={handleContinue}
              disabled={isPending}
            >
              {isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowRight className="h-4 w-4" />
              )}
              Continue to Profiling
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
