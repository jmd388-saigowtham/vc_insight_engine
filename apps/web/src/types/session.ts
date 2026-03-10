export interface Session {
  id: string;
  company_name: string;
  industry: string;
  business_context: string;
  current_step: string;
  status: "active" | "completed" | "failed";
  step_states: Record<string, string> | null;
  target_column: string | null;
  selected_features: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface SessionCreate {
  company_name: string;
  industry: string;
  business_context: string;
}
