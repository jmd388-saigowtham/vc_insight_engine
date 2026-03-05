export interface UploadedFile {
  id: string;
  session_id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  row_count: number | null;
  column_count: number | null;
  uploaded_at: string;
}

export interface ColumnProfile {
  id: string;
  file_id: string;
  column_name: string;
  data_type: string;
  null_percentage: number;
  unique_count: number;
  min_value: string | null;
  max_value: string | null;
  mean_value: number | null;
  sample_values: string[];
  description: string | null;
}

export interface TableProfile {
  file: UploadedFile;
  columns: ColumnProfile[];
}

export interface CodeProposal {
  id: string;
  session_id: string;
  step: string;
  language: string;
  code: string;
  description: string;
  status: "pending" | "approved" | "denied";
}

export interface Artifact {
  id: string;
  session_id: string;
  step: string;
  artifact_type: "image" | "html" | "json" | "csv" | "text";
  title: string;
  description: string;
  file_path: string | null;
  data: Record<string, unknown> | null;
  created_at: string;
}

export interface Hypothesis {
  id: string;
  session_id: string;
  statement: string;
  test_type: string;
  variables: string[];
  expected_outcome: string;
  status: "pending" | "approved" | "rejected";
  result: HypothesisResult | null;
}

export interface HypothesisResult {
  test_statistic: number;
  p_value: number;
  conclusion: string;
  supported: boolean;
}

export interface ModelResult {
  id: string;
  session_id: string;
  model_name: string;
  accuracy: number;
  precision: number;
  recall: number;
  f1_score: number;
  auc_roc: number;
  is_best: boolean;
  confusion_matrix: number[][] | null;
}

export interface Report {
  id: string;
  session_id: string;
  executive_summary: string;
  key_findings: string[];
  recommendations: string[];
  export_urls: {
    pdf?: string;
    pptx?: string;
    csv?: string;
  };
}
