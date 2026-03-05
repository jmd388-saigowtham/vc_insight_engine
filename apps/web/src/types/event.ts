export type EventType =
  | "PLAN"
  | "TOOL_CALL"
  | "TOOL_RESULT"
  | "CODE_PROPOSED"
  | "CODE_APPROVED"
  | "CODE_DENIED"
  | "EXEC_START"
  | "EXEC_END"
  | "ERROR"
  | "INFO"
  | "STEP_START"
  | "STEP_END";

export interface TraceEvent {
  id: string;
  session_id: string;
  event_type: EventType;
  step: string;
  payload: Record<string, unknown>;
  created_at: string;
}
