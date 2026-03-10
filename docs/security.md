# Security Considerations

## Sandbox Execution Model

AI-generated code runs through a multi-layer security pipeline before execution.

### AST-Based Static Analysis

Before any code is executed, the `sandbox_executor` performs static analysis by parsing the code into an AST and walking it for dangerous patterns:

**Blocked function calls:**
`eval`, `exec`, `compile`, `__import__`, `getattr`, `setattr`, `delattr`, `globals`, `locals`, `breakpoint`, `exit`, `quit`

**Blocked attribute chains:**
`os.system`, `os.popen`, `os.remove`, `os.unlink`, `os.rmdir`, `subprocess.call`, `subprocess.run`, `subprocess.Popen`, `subprocess.check_output`, `shutil.rmtree`, `shutil.move`

Code that fails validation is rejected with a detailed error before reaching the subprocess.

### Import Allowlist

Only pre-approved modules can be imported. The allowlist includes 35 modules:

- **Data science:** pandas, numpy, scipy, sklearn, matplotlib, plotly, seaborn, shap
- **Standard library:** math, statistics, collections, itertools, functools, datetime, json, csv, re, pathlib, typing, dataclasses, textwrap, io, decimal, fractions, copy, operator, string, enum, abc, warnings
- **Utilities:** pydantic, openpyxl, joblib, pickle

Any import not in this list is rejected during static analysis.

### Subprocess Isolation

Code executes in a separate Python subprocess, not in the API process:

- Configurable timeout (default 60 seconds). Returns exit code 124 on timeout.
- Stdout and stderr are captured and stored.
- Execution runs in a temporary working directory.
- The temp script file is cleaned up after execution.
- Newly created files are detected by comparing directory contents before and after execution.

### Human-in-the-Loop Approval

All agent-generated code must be explicitly approved by the user before execution:

1. Code is surfaced via SSE as a `CODE_PROPOSED` event.
2. The user reviews it in a Monaco editor modal.
3. The user can approve, deny, or edit before approving.
4. Only approved code is sent to the sandbox executor.
5. The pipeline pauses (`next_action = "wait"`) until the user acts.

## Rate Limiting

In-memory rate limiting is applied via `RateLimitMiddleware`:

| Scope | Limit |
|-------|-------|
| General API requests | 100 requests/minute |
| Upload endpoints (`/upload`) | 10 requests/minute |

Rate limit state is **in-memory** and resets on server restart. Returns `429 Too Many Requests` when exceeded.

## File Upload Validation

- **Accepted formats:** CSV and XLSX only. File extension is validated.
- **Maximum file size:** Configurable via `MAX_UPLOAD_SIZE_MB` (default 500 MB).
- **Filename sanitization:** Uploaded files are stored with generated UUIDs, not original filenames.
- **Storage:** Files are stored outside the web-accessible root in `UPLOAD_DIR`.

## Path Traversal Protection

Artifact file serving (`GET /artifacts/{id}/file`) includes path traversal protection:

1. The artifact's `storage_path` is resolved to an absolute path.
2. It is checked with `is_relative_to()` against the configured `UPLOAD_DIR`.
3. If the resolved path escapes the upload directory, the request is rejected with `403 Access Denied`.

The `StorageService` also implements `_validate_path()` for all file operations.

## CORS Policy

- CORS origins are configured via the `CORS_ORIGINS` environment variable.
- The default development configuration allows both `http://localhost:3000` and `http://localhost:3001` (Next.js auto-selects port 3001 when 3000 is in use).
- Credentials, all headers, and all methods are allowed in development.
- In production, restrict to the exact frontend domain.

## Environment Variable Management

- Secrets (database credentials, API keys) are provided via environment variables, never committed to the repository.
- The `.env` file is gitignored. `.env.example` contains placeholder values.
- In production, use a secrets manager (Azure Key Vault, AWS Secrets Manager) or CI/CD secret injection.
- The `AZURE_OPENAI_API_KEY` should be rotated regularly and scoped to minimum required permissions.

## Network Security

- Internal services (PostgreSQL, Redis) are only accessible within the Docker network (`vcnet`). Expose ports to the host only in development.
- The nginx reverse proxy terminates external traffic and forwards to internal services.
- SSE endpoints use `X-Accel-Buffering: no` header for nginx compatibility.
- In production, add TLS termination at the nginx or load balancer layer.
- Redis is used only for the Arq task queue; SSE streaming uses in-memory queues within the API process.

## Authentication

Authentication is not included in the current implementation. Before production deployment, add an authentication layer (OAuth 2.0, API keys, or session-based auth) to protect all API endpoints. Key areas to secure:

- Session creation and data access
- File upload and artifact download
- Code approval endpoints
- Pipeline execution triggers
- Admin cleanup endpoint
- SSE event streams
