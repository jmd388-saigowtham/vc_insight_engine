# API Reference

Base URL: `http://localhost:8000`

## Health

### `GET /health`

Returns service health status.

**Response** `200 OK`
```json
{ "status": "healthy", "version": "0.1.0" }
```

---

## Sessions

### `POST /api/sessions`

Create a new analysis session.

**Request Body**
```json
{ "name": "Q4 Deal Flow Analysis", "upload_ids": ["uuid"] }
```

**Response** `201 Created`
```json
{ "id": "uuid", "name": "...", "status": "created", "created_at": "..." }
```

### `GET /api/sessions`

List all sessions. Supports `?status=` filter and `?limit=`/`?offset=` pagination.

### `GET /api/sessions/{session_id}`

Get session details including associated uploads and latest events.

### `DELETE /api/sessions/{session_id}`

Delete a session and its associated artifacts.

---

## Uploads

### `POST /api/uploads`

Upload a CSV or Excel file. Uses `multipart/form-data`.

**Form Fields**
- `file` (required): The file to upload (max 500 MB)

**Response** `201 Created`
```json
{ "id": "uuid", "filename": "deals.csv", "size_bytes": 102400, "created_at": "..." }
```

### `GET /api/uploads`

List all uploaded files.

### `GET /api/uploads/{upload_id}`

Get upload metadata.

---

## Profiling

### `GET /api/uploads/{upload_id}/profile`

Get column-level profiling results for an upload.

**Response** `200 OK`
```json
{
  "upload_id": "uuid",
  "row_count": 1500,
  "columns": [
    {
      "name": "deal_size",
      "dtype": "float64",
      "null_count": 12,
      "null_pct": 0.8,
      "unique_count": 487,
      "min": 50000,
      "max": 25000000,
      "mean": 3200000
    }
  ]
}
```

---

## Events (SSE)

### `GET /api/sessions/{session_id}/events/stream`

Server-Sent Events stream for real-time session updates.

**Event Types**
- `agent:thinking` -- Agent is processing
- `agent:code` -- Agent generated code for review
- `agent:result` -- Execution result available
- `agent:error` -- An error occurred
- `session:status` -- Session status changed

---

## Code Approval

### `POST /api/sessions/{session_id}/code/{code_id}/approve`

Approve generated code for execution.

### `POST /api/sessions/{session_id}/code/{code_id}/deny`

Deny generated code. Optionally include feedback.

**Request Body**
```json
{ "feedback": "Please use a different chart type." }
```

---

## Artifacts

### `GET /api/sessions/{session_id}/artifacts`

List all artifacts produced in a session.

### `GET /api/sessions/{session_id}/artifacts/{artifact_id}`

Get a specific artifact (data table, chart image, or summary text).
