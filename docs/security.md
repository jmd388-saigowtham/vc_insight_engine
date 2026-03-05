# Security Considerations

## Sandbox Execution Model

AI-generated code runs in an isolated execution environment:

- Code executes in a restricted Python subprocess with limited imports and no filesystem access outside the upload directory.
- Execution is time-bounded (default 30-second timeout) to prevent runaway processes.
- All code must be explicitly approved by the user before execution. The agent cannot execute code autonomously.
- Standard output, errors, and return values are captured and stored as artifacts.

## File Upload Validation

- Accepted formats: CSV, XLSX, XLS only. MIME type and file extension are both validated.
- Maximum file size is configurable via `MAX_UPLOAD_SIZE_MB` (default 500 MB).
- Uploaded filenames are sanitized and stored with generated UUIDs to prevent path traversal.
- Files are stored outside the web-accessible root.

## CORS Policy

- CORS origins are configured via the `CORS_ORIGINS` environment variable.
- In production, restrict to the exact frontend domain. The default development value allows `http://localhost:3000` only.
- Credentials, headers, and methods are explicitly configured in the FastAPI CORS middleware.

## Environment Variable Management

- Secrets (database credentials, API keys) are provided via environment variables, never committed to the repository.
- The `.env` file is gitignored. `.env.example` contains placeholder values for documentation.
- In production, use a secrets manager (Azure Key Vault, AWS Secrets Manager) or CI/CD secret injection rather than `.env` files.
- The `AZURE_OPENAI_API_KEY` should be rotated regularly and scoped to the minimum required permissions.

## Network Security

- Internal services (PostgreSQL, Redis) are only accessible within the Docker network (`vcnet`). Expose ports to the host only in development.
- The nginx reverse proxy terminates external traffic and forwards to internal services.
- In production, add TLS termination at the nginx or load balancer layer.

## Authentication

- Authentication is not included in the initial scaffold. Before production deployment, add an authentication layer (OAuth 2.0, API keys, or session-based auth) to protect all API endpoints.
