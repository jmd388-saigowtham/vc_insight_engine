# API Reference

Base URL: `http://localhost:8000`

All endpoints are async. UUIDs are used for all entity IDs. Responses use `application/json` unless otherwise noted.

---

## Health

### `GET /health`

Returns service health status.

**Response** `200 OK`
```json
{ "status": "ok", "version": "0.1.0" }
```

---

## Sessions

Router prefix: `/sessions`

### `POST /sessions`

Create a new analysis session.

**Request Body**
```json
{
  "company_name": "Acme Corp",
  "industry": "SaaS",
  "business_context": "Analyze churn drivers for Series B portfolio company"
}
```

**Response** `201 Created` — `SessionResponse`

### `GET /sessions`

List all sessions. Supports `?limit=` (default 50) and `?offset=` pagination.

**Response** `200 OK` — `SessionResponse[]`

### `GET /sessions/{session_id}`

Get session details.

**Response** `200 OK` — `SessionResponse`

### `PATCH /sessions/{session_id}`

Update session fields (company_name, industry, current_step, status, target_column, selected_features, step_states).

**Request Body** — partial `SessionUpdate`

**Response** `200 OK` — `SessionResponse`

### `POST /sessions/{session_id}/business-context`

Update the business context for a session.

**Request Body**
```json
{ "business_context": "Focus on expansion revenue opportunities" }
```

**Response** `200 OK` — `SessionResponse`

---

## Uploads

### `POST /sessions/{session_id}/upload`

Upload a CSV or Excel file. Uses `multipart/form-data`. Auto-profiles columns on upload.

**Form Fields**
- `file` (required): CSV or XLSX file (max 500 MB, configurable)

**Response** `201 Created` — `UploadResponse`
```json
{
  "id": "uuid",
  "session_id": "uuid",
  "filename": "customers.csv",
  "original_filename": "customers.csv",
  "file_type": "csv",
  "size_bytes": 102400,
  "row_count": 5000,
  "column_count": 12,
  "created_at": "2025-01-15T10:30:00Z"
}
```

### `GET /sessions/{session_id}/files`

List all uploaded files for a session.

**Response** `200 OK` — `FileListResponse`
```json
{ "files": [...], "total": 2 }
```

### `GET /files/{file_id}`

Get a single file's metadata.

**Response** `200 OK` — `UploadResponse`

---

## Profiling

### `GET /files/{file_id}/profile`

Get column-level profiling results for an uploaded file.

**Response** `200 OK` — `ColumnProfileResponse[]`
```json
[
  {
    "id": "uuid",
    "file_id": "uuid",
    "column_name": "deal_size",
    "dtype": "float64",
    "null_count": 12,
    "null_pct": 0.8,
    "unique_count": 487,
    "min_value": "50000",
    "max_value": "25000000",
    "mean_value": "3200000",
    "sample_values": ["100000", "500000", "1200000"],
    "description": null
  }
]
```

### `PATCH /columns/{column_id}/description`

Update a column's user-provided description.

**Request Body**
```json
{ "description": "Annual contract value in USD" }
```

**Response** `200 OK` — `ColumnProfileResponse`

### `GET /sessions/{session_id}/tables`

Get all tables (files + column profiles) for a session.

**Response** `200 OK` — `ProfileSummary[]`

---

## Events

### `GET /sessions/{session_id}/events/stream`

Server-Sent Events stream for real-time session updates.

**Headers**
- `Cache-Control: no-cache`
- `Connection: keep-alive`
- `X-Accel-Buffering: no`

Sends 15-second keepalive pings. Supports `Last-Event-ID` header for reconnection.

**Event Format**
```
id: <event_id>
event: message
data: {"event_type": "STEP_START", "step": "profiling", "payload": {...}, "created_at": "..."}
```

### `GET /sessions/{session_id}/events`

Get paginated event history. Supports `?limit=` (default 50) and `?offset=`.

**Response** `200 OK` — `TraceEventResponse[]`

### Event Types

| Type | Description |
|------|-------------|
| `PLAN` | Agent planning output |
| `TOOL_CALL` | MCP tool invocation |
| `TOOL_RESULT` | MCP tool response |
| `CODE_PROPOSED` | Code generated for approval |
| `CODE_APPROVED` | User approved code execution |
| `CODE_DENIED` | User denied code execution |
| `CODE_EDITED` | User edited code before approval |
| `EXEC_START` | Code execution started |
| `EXEC_END` | Code execution completed |
| `ERROR` | Error occurred |
| `WARNING` | Non-fatal warning |
| `INFO` | Informational message |
| `STEP_START` | Pipeline step started |
| `STEP_END` | Pipeline step completed |
| `STEP_STALE` | Step invalidated by upstream rerun |
| `DECISION` | Orchestrator decision (next action) |
| `ARTIFACT` | New artifact created |
| `USER_INPUT` | User input received |

---

## Code Approval

### `GET /sessions/{session_id}/code/pending`

Get the most recent pending code proposal for a session.

**Response** `200 OK` — `CodeProposalResponse | null`
```json
{
  "id": "uuid",
  "session_id": "uuid",
  "step": "eda",
  "code": "import pandas as pd\n...",
  "language": "python",
  "description": "Generate distribution plots",
  "status": "pending",
  "created_at": "..."
}
```

### `POST /code/{proposal_id}/approve`

Approve a pending code proposal. Emits a `CODE_APPROVED` event.

**Request Body** (optional)
```json
{ "feedback": "" }
```

**Response** `200 OK` — `CodeProposalResponse` (status: `approved`)

Returns `409 Conflict` if the proposal is not in `pending` status.

### `POST /code/{proposal_id}/deny`

Deny a pending code proposal. Emits a `CODE_DENIED` event.

**Request Body** (optional)
```json
{ "feedback": "Please use a bar chart instead" }
```

**Response** `200 OK` — `CodeProposalResponse` (status: `denied`)

---

## Artifacts

### `GET /sessions/{session_id}/artifacts`

List all artifacts for a session. Supports `?step=` filter.

**Response** `200 OK`
```json
[
  {
    "id": "uuid",
    "session_id": "uuid",
    "step": "eda",
    "artifact_type": "image",
    "title": "Distribution: deal_size",
    "description": "Histogram of deal_size column",
    "file_path": "/artifacts/<id>/file",
    "data": {},
    "created_at": "..."
  }
]
```

### `GET /artifacts/{artifact_id}`

Get artifact metadata.

**Response** `200 OK` — `ArtifactResponse`

### `GET /artifacts/{artifact_id}/file`

Serve an artifact file with the correct media type (PNG, SVG, JSON, CSV, etc.) for inline browser rendering. Path traversal protection ensures files are within the upload directory.

**Response** `200 OK` — file content with appropriate `Content-Type`

### `GET /artifacts/{artifact_id}/download`

Download an artifact as an attachment.

**Response** `200 OK` — `application/octet-stream` with `Content-Disposition: attachment`

---

## Pipeline

### `POST /sessions/{session_id}/run-pipeline`

Trigger the AI analysis pipeline.

**Request Body** (optional)
```json
{ "step": "eda" }
```

If `step` is provided, runs only that step. Otherwise runs the full pipeline.

**Response** `200 OK`

### `POST /sessions/{session_id}/rerun/{step}`

Invalidate all downstream steps and rerun from a specific step. Uses BFS through the dependency graph to mark downstream steps as `STALE`.

Returns `400` if the step name is invalid. Returns `409` if steps are already running.

**Response** `200 OK`

### `POST /sessions/{session_id}/resume`

Resume the pipeline after a code approval or denial.

**Request Body** (optional)
```json
{ "proposal_id": "uuid" }
```

Returns `409` if steps are already running.

**Response** `200 OK`

### `POST /sessions/{session_id}/complete`

Mark a session as completed.

**Response** `200 OK`
```json
{ "status": "completed" }
```

---

## Pipeline Data Endpoints

### `GET /sessions/{session_id}/opportunities`

Get AI-identified value creation opportunities. Auto-triggers the pipeline on first call if no artifacts exist.

**Response** `200 OK` — `OpportunityResponse[]`

### `GET /sessions/{session_id}/target`

Get the identified target variable and feature preview.

**Response** `200 OK` — `TargetConfigResponse`

### `GET /sessions/{session_id}/hypotheses`

Get generated hypotheses. Supports `?with_results=true` to include test results.

**Response** `200 OK` — `HypothesisResponse[]`

### `PATCH /hypotheses/{hypothesis_id}`

Update hypothesis status (approve or reject).

**Request Body**
```json
{ "status": "approved" }
```

**Response** `200 OK` — `HypothesisResponse`

### `GET /sessions/{session_id}/models`

Get model training results.

**Response** `200 OK` — `ModelResultResponse[]`
```json
[
  {
    "id": "uuid",
    "session_id": "uuid",
    "model_name": "random_forest",
    "accuracy": 0.87,
    "precision": 0.85,
    "recall": 0.82,
    "f1_score": 0.83,
    "auc_roc": 0.91,
    "is_best": true,
    "confusion_matrix": [[120, 15], [22, 93]]
  }
]
```

### `GET /sessions/{session_id}/report`

Get the final analysis report.

**Response** `200 OK` — `ReportResponse`
```json
{
  "id": "uuid",
  "session_id": "uuid",
  "executive_summary": "...",
  "key_findings": ["..."],
  "recommendations": ["..."],
  "export_urls": { "pdf": "/artifacts/uuid/download" }
}
```

---

## Feature Selection

### `GET /sessions/{session_id}/feature-selection`

Get the current feature selection state. Returns all columns (excluding target), their profiles, and selection status.

**Response** `200 OK` — `FeatureSelectionResponse`
```json
{
  "target_column": "churned",
  "features": [
    {
      "name": "tenure_months",
      "dtype": "int64",
      "null_pct": 0.0,
      "unique_count": 48,
      "importance": 0.5,
      "selected": true
    }
  ],
  "selected_features": ["tenure_months", "monthly_charges"]
}
```

### `PATCH /sessions/{session_id}/feature-selection`

Update target column and selected features.

**Request Body**
```json
{
  "target_column": "churned",
  "selected_features": ["tenure_months", "monthly_charges", "contract_type"]
}
```

Returns `400` if no features are selected or if the target column is in the selected features list.

**Response** `200 OK`

---

## Step States

### `GET /sessions/{session_id}/step-states`

Get current step states for all pipeline steps.

**Response** `200 OK`
```json
{
  "step_states": {
    "profiling": "DONE",
    "merge_planning": "DONE",
    "target_id": "DONE",
    "feature_selection": "READY",
    "eda": "NOT_STARTED",
    "preprocessing": "NOT_STARTED",
    "hypothesis": "NOT_STARTED",
    "feature_eng": "NOT_STARTED",
    "modeling": "NOT_STARTED",
    "explainability": "NOT_STARTED",
    "recommendation": "NOT_STARTED",
    "report": "NOT_STARTED"
  }
}
```

---

## Admin

### `POST /admin/cleanup`

Delete uploaded files older than `max_age_days` (default 30) for completed sessions.

**Query Parameters**
- `max_age_days` (optional, default 30)

**Response** `200 OK`
```json
{ "deleted_count": 5 }
```
