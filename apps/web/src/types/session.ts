export interface Session {
  id: string;
  company_name: string;
  industry: string;
  business_context: string;
  current_step: string;
  status: "active" | "completed" | "failed";
  created_at: string;
  updated_at: string;
}

export interface SessionCreate {
  company_name: string;
  industry: string;
  business_context: string;
}
