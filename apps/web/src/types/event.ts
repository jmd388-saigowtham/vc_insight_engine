export type EventType =
  | "PLAN"
  | "TOOL_CALL"
  | "TOOL_RESULT"
  | "CODE_PROPOSED"
  | "CODE_APPROVED"
  | "CODE_DENIED"
  | "CODE_EDITED"
  | "CODE_REUSE"
  | "EXEC_START"
  | "EXEC_END"
  | "ERROR"
  | "INFO"
  | "STEP_START"
  | "STEP_END"
  | "DECISION"
  | "AI_REASONING"
  | "TOOL_DISCOVERY"
  | "DOC_UPDATED"
  | "ARTIFACT_CREATED"
  | "ARTIFACT"
  | "MODEL_SELECTION"
  | "STAGE_RERUN"
  | "FINAL_SUMMARY"
  | "WARNING"
  | "USER_INPUT"
  | "STEP_STALE"
  | "PROPOSAL_CREATED"
  | "PROPOSAL_APPROVED"
  | "PROPOSAL_REVISED"
  | "PROPOSAL_REJECTED"
  | "STAGE_MARKED_STALE"
  | "USER_FEEDBACK"
  | "STAGE_RUNNING"
  | "STAGE_DONE"
  | "OBSERVATION"
  | "REFLECTION"
  | "RETRY";

export interface TraceEvent {
  id: string;
  session_id: string;
  event_type: EventType;
  step: string;
  payload: Record<string, unknown>;
  created_at: string;
}
