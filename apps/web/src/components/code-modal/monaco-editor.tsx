"use client";

import dynamic from "next/dynamic";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[400px] items-center justify-center rounded-md border bg-muted">
      <p className="text-sm text-muted-foreground">Loading editor...</p>
    </div>
  ),
});

export default MonacoEditor;
