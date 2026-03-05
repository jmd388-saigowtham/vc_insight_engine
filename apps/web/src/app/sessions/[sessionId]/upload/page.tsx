"use client";

import { useParams, useRouter } from "next/navigation";
import { useTables, useUploadFile } from "@/hooks/use-tables";
import { useUpdateSession } from "@/hooks/use-session";
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
import { ArrowRight, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function UploadPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;
  const { data: tables, isLoading } = useTables(sessionId);
  const uploadFile = useUploadFile(sessionId);
  const updateSession = useUpdateSession(sessionId);

  const files = tables?.map((t) => t.file) ?? [];

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
    updateSession.mutate(
      { current_step: "profiling" },
      {
        onSuccess: () =>
          router.push(`/sessions/${sessionId}/profiling`),
      },
    );
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

          {files.length > 0 && (
            <Button
              className="w-full gap-2"
              onClick={handleContinue}
              disabled={updateSession.isPending}
            >
              {updateSession.isPending ? (
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
