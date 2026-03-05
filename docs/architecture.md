# Architecture

## System Overview

VC Insight Engine is a full-stack application that enables venture capital analysts to upload datasets, profile data quality, and run AI-driven analysis through an interactive agent workflow with human-in-the-loop code approval.

```
Browser (Next.js) <---> FastAPI <---> PostgreSQL
                          |
                       Redis (queues + SSE)
                          |
                       ARQ Workers (AI Agent)
```

## Components

| Component     | Technology            | Role                                      |
| ------------- | --------------------- | ----------------------------------------- |
| **Frontend**  | Next.js 14 (App Router) | Dashboard UI, file upload, session management, SSE event stream |
| **API**       | FastAPI + Uvicorn     | REST endpoints, SSE streaming, file handling |
| **Workers**   | ARQ (async Redis)     | Background profiling, AI agent execution  |
| **Database**  | PostgreSQL 16         | Sessions, uploads, profiles, artifacts    |
| **Cache/Queue** | Redis 7             | Task queue, SSE pub/sub                   |
| **AI**        | Azure OpenAI (GPT-4o) | Code generation, data analysis            |

## Data Flow

1. **Upload** -- User uploads CSV/Excel files via the web UI. Files are stored on disk; metadata is saved to PostgreSQL.
2. **Profile** -- An ARQ worker reads the uploaded file, computes column-level statistics (types, nulls, distributions), and stores results.
3. **AI Agent** -- The user starts an analysis session. The AI agent generates Python code to answer analytical questions about the data.
4. **Code Approval** -- Generated code is surfaced to the user via SSE for review. The user approves or denies execution.
5. **Execution** -- Approved code runs in a sandboxed environment. Results (DataFrames, charts) are captured as artifacts.
6. **Results** -- Artifacts are stored and displayed in the UI. The agent can iterate based on results.

## Directory Structure

```
vc engine/
  apps/
    api/          # FastAPI backend
    web/          # Next.js frontend
  packages/
    mcp-tools/    # MCP tool servers for the AI agent
    shared/       # Shared types and utilities
  infra/          # Docker, nginx, DB init scripts
  data/uploads/   # Uploaded files (gitignored)
  docs/           # Documentation
```
