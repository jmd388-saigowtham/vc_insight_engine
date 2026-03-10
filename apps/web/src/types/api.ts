export interface FeatureSelectionData {
  target_column: string;
  features: {
    name: string;
    importance: number;
    reasoning: string;
    selected: boolean;
    source?: string;
    leakage_risk?: boolean;
  }[];
}

export interface UploadedFile {
  id: string;
  session_id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  row_count: number | null;
  column_count: number | null;
  created_at: string;
}

export interface ColumnProfile {
  id: string;
  file_id: string;
  column_name: string;
  dtype: string;
  null_count: number | null;
  null_pct: number | null;
  unique_count: number | null;
  min_value: string | null;
  max_value: string | null;
  mean_value: number | null;
  sample_values: unknown[] | null;
  description: string | null;
}

export interface TableProfile {
  file_id: string;
  filename: string;
  row_count: number | null;
  column_count: number | null;
  columns: ColumnProfile[];
}

export interface CodeContext {
  ai_explanation: string;
  tool_tried: string;
  tool_insufficiency: string;
  alternative_strategies: string[];
  denial_count: number;
  max_denials: number;
  denial_feedback: string[];
}

export interface CodeProposal {
  id: string;
  session_id: string;
  step: string;
  language: string;
  code: string;
  description: string;
  status: "pending" | "approved" | "denied";
  node_name?: string;
  context?: CodeContext;
}

export interface Artifact {
  id: string;
  session_id: string;
  step: string;
  artifact_type: string;  // "eda" | "shap" | "model" | "hypothesis" | "report" | etc
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

export interface ModelMetrics {
  accuracy: number;
  precision: number;
  recall: number;
  f1: number;
  roc_auc: number;
}

export interface ModelDiagnostics {
  status: "good_fit" | "overfitting" | "underfitting";
  message: string;
  train_test_gap: number;
  primary_metric: string;
  threshold_info?: ThresholdInfo;
}

export interface ThresholdInfo {
  threshold: number;
  method: string;
  f1_at_threshold?: number;
  precision_at_threshold?: number;
  recall_at_threshold?: number;
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
  train_metrics: ModelMetrics | null;
  val_metrics: ModelMetrics | null;
  diagnostics: ModelDiagnostics | null;
  threshold_info: ThresholdInfo | null;
}

export interface DatasetEntry {
  id: string;
  session_id: string;
  source_type: string;
  name: string;
  file_path: string;
  row_count: number | null;
  column_count: number | null;
  parent_dataset_id: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string | null;
}

export interface BusinessProposal {
  id: string;
  session_id: string;
  step: string;
  proposal_type: string;
  status: "pending" | "approved" | "revised" | "rejected";
  version: number;
  plan: Record<string, unknown> | null;
  summary: string | null;
  ai_reasoning: string | null;
  alternatives: Record<string, unknown>[] | null;
  user_feedback: string | null;
  parent_id: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface UserFeedbackEntry {
  id: string;
  session_id: string;
  step: string | null;
  message: string;
  status: "pending" | "acknowledged" | "applied";
  created_at: string;
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
    json?: string;
  };
}
