"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";
import { Upload, FileSpreadsheet } from "lucide-react";

interface DropzoneProps {
  onUpload: (file: File, onProgress: (pct: number) => void) => Promise<void>;
  disabled?: boolean;
}

export function Dropzone({ onUpload, disabled }: DropzoneProps) {
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentFile, setCurrentFile] = useState<string | null>(null);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      for (const file of acceptedFiles) {
        setUploading(true);
        setCurrentFile(file.name);
        setProgress(0);
        try {
          await onUpload(file, setProgress);
        } catch {
          // error handled by parent
        }
      }
      setUploading(false);
      setCurrentFile(null);
      setProgress(0);
    },
    [onUpload],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
        ".xlsx",
      ],
    },
    maxSize: 500 * 1024 * 1024,
    disabled: disabled || uploading,
  });

  return (
    <div className="space-y-3">
      <div
        {...getRootProps()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-12 transition-colors",
          isDragActive
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-primary/50",
          (disabled || uploading) && "cursor-not-allowed opacity-50",
        )}
      >
        <input {...getInputProps()} />
        {isDragActive ? (
          <>
            <FileSpreadsheet className="mb-3 h-10 w-10 text-primary" />
            <p className="text-sm font-medium text-primary">
              Drop files here...
            </p>
          </>
        ) : (
          <>
            <Upload className="mb-3 h-10 w-10 text-muted-foreground" />
            <p className="mb-1 text-sm font-medium">
              Drag & drop files here, or click to browse
            </p>
            <p className="text-xs text-muted-foreground">
              CSV or XLSX files up to 500MB
            </p>
          </>
        )}
      </div>

      {uploading && currentFile && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="truncate">{currentFile}</span>
            <span className="text-muted-foreground">{progress}%</span>
          </div>
          <Progress value={progress} className="h-2" />
        </div>
      )}
    </div>
  );
}
