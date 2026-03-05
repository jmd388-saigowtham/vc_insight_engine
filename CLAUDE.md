# CLAUDE.md — VC Insight Engine

## Project Overview

VC Insight Engine is a production-grade **Autonomous Agentic Data Science Platform** for venture capital firms. It enables AI-orchestrated data science workflows — from data upload through ML modeling and SHAP explainability — with real-time UI tracing and human-in-the-loop code approval.

**Use Case:** VC firms assess data-driven value creation opportunities (churn, expansion, cross-sell, upsell) for portfolio companies.

## Architecture

```
[Next.js 15 Frontend] <--SSE/REST--> [FastAPI Backend] <--Arq/Redis--> [Worker]
       (port 3000)                      (port 8000)                       |
                                            |                       [LangGraph Agent]
                                       [PostgreSQL]                       |
                                       (port 5432)              [10 MCP Tool Servers]
                                            |                             |
                                      [7 DB Tables]             [Sandbox Executor]
```

## Repository Structure

```
vc-engine/
├── apps/
│   ├── api/           # FastAPI backend (Python 3.12+)
│   │   ├── src/app/   # Application source
│   │   ├── alembic/   # Database migrations
│   │   └── tests/     # pytest test suite
│   └── web/           # Next.js 15 frontend (Node 20+)
│       └── src/       # Application source
├── packages/
│   ├── mcp-servers/   # 10 Python tool servers
│   └── shared/        # Shared Pydantic schemas
├── infra/             # Docker Compose, nginx, init.sql
├── docs/              # Architecture, API, security docs
└── data/uploads/      # Local file storage (gitignored)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, async SQLAlchemy 2.0, asyncpg, Pydantic v2, structlog |
| Database | PostgreSQL 16 (JSONB, UUID), Alembic migrations |
| Task Queue | Arq (Redis-backed async worker) |
| AI/ML | LangGraph state machine, LangChain, Azure OpenAI, scikit-learn, SHAP |
| Frontend | Next.js 15 App Router, React 19, TypeScript 5.7 |
| UI | Tailwind CSS 3.4, Radix UI primitives, shadcn/ui patterns, Lucide icons |
| State | Zustand (client state), TanStack React Query (server state) |
| Streaming | Server-Sent Events (SSE) with asyncio.Queue pub/sub |
| Code Editor | Monaco Editor (dynamic import, no SSR) |

## Common Commands

### Backend (apps/api/)
```bash
# Install dependencies
cd apps/api && pip install -e ".[dev]"

# Run API server
cd apps/api && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run Arq worker
cd apps/api && python -m arq app.worker.main.WorkerSettings

# Run tests
cd apps/api && python -m pytest tests/ -x --tb=short

# Lint
cd apps/api && python -m ruff check src/

# Run Alembic migration
cd apps/api && alembic upgrade head
```

### Frontend (apps/web/)
```bash
# Install dependencies
cd apps/web && npm install

# Dev server
cd apps/web && npm run dev

# Type check
cd apps/web && npx tsc --noEmit

# Run tests
cd apps/web && npx vitest run

# Build
cd apps/web && npm run build
```

### Docker (full stack)
```bash
# Start all services
docker compose -f infra/docker-compose.yml up

# Dev mode with hot reload
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up
```

## Backend Architecture

### Entry Point & Config
- **`src/app/main.py`** — FastAPI app factory with lifespan, CORS, structlog, router includes
- **`src/app/config.py`** — Pydantic BaseSettings loading from `.env`
- **`src/app/database.py`** — Async SQLAlchemy engine (pool_size=20, max_overflow=10) + `get_db()` generator
- **`src/app/dependencies.py`** — DI providers: `get_settings()`, `get_db_session()`, `get_event_service()`, `get_storage_service()`

### Database Models (`src/app/models/`)
All models inherit from `Base` (DeclarativeBase) and use mixins:
- **`UUIDMixin`** — UUID primary key with `uuid.uuid4` default
- **`TimestampMixin`** — `created_at` with `server_default=func.now()`
- **`FullTimestampMixin`** — adds `updated_at` with `onupdate=func.now()`

**7 tables:** sessions, uploaded_files, column_profiles, trace_events, code_proposals, artifacts, session_context_docs

**Important patterns:**
- Use `Mapped[]` type annotations (SQLAlchemy 2.0 style)
- PostgreSQL-specific types: `UUID(as_uuid=True)`, `JSONB` from `sqlalchemy.dialects.postgresql`
- Use `TIMESTAMP(timezone=True)` for timezone-aware columns — NOT `TIMESTAMPTZ` (not importable)
- All FK relationships use `ondelete="CASCADE"`
- Indexes on `session_id` and `created_at` for all event/file tables

### Pydantic Schemas (`src/app/schemas/`)
- All response schemas use `model_config = ConfigDict(from_attributes=True)` for ORM conversion
- Separate Create/Update/Response models per entity
- Located in: `session.py`, `upload.py`, `profile.py`, `event.py`, `code.py`

### Routers (`src/app/routers/`)
| Router | Prefix | Key Endpoints |
|--------|--------|---------------|
| health | `/health` | GET (status + version) |
| sessions | `/sessions` | CRUD + business-context |
| uploads | `/sessions/{id}` | POST /upload (multipart), GET /files |
| profiling | `/files/{id}` | GET /profile, PATCH /columns/{id}/description |
| events | `/sessions/{id}` | GET /events/stream (SSE), GET /events (paginated) |
| code | `/sessions/{id}` | GET /code/pending, POST /code/{id}/approve\|deny |
| artifacts | `/sessions/{id}` | GET /artifacts, GET /artifacts/{id}/download |

**Pattern:** Each router injects services via `Depends()`. Service instantiation helper at top of file.

### Services (`src/app/services/`)
- **`event_service.py`** — SSE broadcaster using `defaultdict(list)` of `asyncio.Queue` per session. `emit()` writes to DB and broadcasts. `stream()` yields SSE format with 15s keepalive.
- **`profiling_service.py`** — Pandas profiling with chunked reading for files >100MB. Samples first 100K rows. Computes dtypes, null counts, unique counts, min/max/mean, sample values.
- **`upload_service.py`** — File validation (csv/xlsx only), save to disk with UUID name, create DB record.
- **`storage.py`** — Local filesystem adapter using `settings.upload_dir`.
- **`session_service.py`** — Session CRUD operations.
- **`agent_service.py`** — LangGraph runner stub.

### Agent System (`src/app/agent/`)
- **`state.py`** — `AgentState` TypedDict with 30+ fields covering the full pipeline
- **`graph.py`** — LangGraph `StateGraph` with 11 sequential nodes: profiling → merge_planning → target_id → eda → preprocessing → hypothesis → feature_eng → modeling → explainability → recommendation → report → END
- **`nodes/`** — One file per pipeline step, each a function taking AgentState
- **`tools/mcp_bridge.py`** — Bridge to call MCP tool servers from LangChain

### Worker (`src/app/worker/`)
- **`main.py`** — Arq WorkerSettings with Redis connection, max_jobs=10, job_timeout=600s
- **`tasks.py`** — `run_step()` task that invokes the LangGraph agent

### Testing
- **conftest.py** — Uses SQLite+aiosqlite for tests with compilation hooks mapping `JSONB→JSON` and `UUID→VARCHAR(36)` for SQLite compatibility
- Override `get_db_session` dependency with test session factory
- Uses `httpx.AsyncClient` with `ASGITransport` for endpoint testing

## Frontend Architecture

### App Router Structure (`src/app/`)
- **Root layout** (`layout.tsx`) — ThemeProvider (next-themes), QueryClientProvider, Toaster (sonner)
- **Landing page** (`page.tsx`) — Hero section with "Start New Analysis" button
- **`sessions/new/`** — Creates session via mutation, redirects to onboarding
- **`sessions/[sessionId]/layout.tsx`** — Wizard layout with session context
- **11 wizard pages** under `[sessionId]/`: onboarding, upload, profiling, workspace, target, eda, hypotheses, hypothesis-results, models, shap, report

### Component Patterns
- **UI components** (`components/ui/`) — Follow shadcn/ui pattern: `cn()` utility, `forwardRef`, CVA for variants. All use Radix primitives.
- **"use client"** directive — ONLY on components using hooks, browser APIs, or interactivity. Server components are default.
- **Dynamic imports** — Monaco Editor loaded via `next/dynamic` with `ssr: false`

### Key Components
| Component | Location | Purpose |
|-----------|----------|---------|
| WizardNav | `components/wizard/wizard-nav.tsx` | 11-step horizontal stepper (completed/current/locked) |
| LiveTraceSidebar | `components/live-trace/live-trace-sidebar.tsx` | Collapsible right sidebar, SSE-connected event list |
| TraceEventItem | `components/live-trace/trace-event-item.tsx` | Color-coded event display with expandable JSON |
| CodeApprovalModal | `components/code-modal/code-approval-modal.tsx` | Monaco editor + approve/deny/edit buttons |
| Dropzone | `components/upload/dropzone.tsx` | react-dropzone wrapper with progress |
| ChartGrid | `components/charts/chart-grid.tsx` | Responsive grid of artifact images |

### State Management
| Store | File | State |
|-------|------|-------|
| sessionStore | `stores/session-store.ts` | currentSessionId, session object |
| traceStore | `stores/trace-store.ts` | events[], isConnected boolean |
| modalStore | `stores/modal-store.ts` | isOpen, proposal (CodeProposal) |

### Hooks (TanStack Query)
| Hook | File | Operations |
|------|------|-----------|
| useSession | `hooks/use-session.ts` | GET session, create mutation, update mutation |
| useTables | `hooks/use-tables.ts` | GET tables/profiles, upload mutation, update column desc |
| useArtifacts | `hooks/use-artifacts.ts` | GET artifacts by session |
| useEventStream | `hooks/use-events.ts` | SSE connection, pushes to traceStore |

**Query key pattern:** `["entity", id]` e.g. `["session", sessionId]`

### API Client (`lib/api-client.ts`)
- Base URL from `NEXT_PUBLIC_API_URL` env var (default `http://localhost:8000`)
- `api.get<T>()`, `api.post<T>()`, `api.patch<T>()`, `api.delete<T>()` — typed fetch wrappers
- `uploadFile()` — XHR with FormData and `onProgress` callback
- Includes credentials, JSON content-type headers
- Custom `ApiError` class with status/statusText/body

### SSE Client (`lib/sse-client.ts`)
- `createEventSource<T>()` — Factory with auto-reconnect (3s delay)
- Tracks `lastEventId` for resumption via `Last-Event-ID` header
- Returns `{ close() }` for cleanup

### TypeScript Types (`types/`)
- **`session.ts`** — Session, SessionCreate interfaces
- **`event.ts`** — TraceEvent, EventType union type (12 event types)
- **`api.ts`** — UploadedFile, ColumnProfile, CodeProposal, Artifact, Hypothesis, ModelResult, ShapResult, Report

## MCP Tool Servers (packages/mcp-servers/)

Direct Python function calls with Pydantic I/O schemas (not stdio MCP servers). Each tool is a module under `src/` with `__init__.py` + `server.py`.

| Tool | Purpose | Key Functions |
|------|---------|---------------|
| session_doc | Session context persistence | read(), upsert(), get_section() |
| data_ingest | Data profiling & sampling | profile(), sample(), row_count() |
| dtype_manager | Type casting & validation | cast_column(), validate_types(), suggest_types() |
| merge_planner | Table join detection | detect_keys(), generate_merge_code(), execute_merge() |
| code_registry | Code snippet storage | store(), retrieve(), get_latest() |
| sandbox_executor | Safe code execution | run(), validate_code() — AST analysis + subprocess |
| preprocessing | Data cleaning | handle_missing(), encode_categorical(), scale_numeric() |
| eda_plots | Chart generation | distribution_plot(), correlation_matrix(), scatter_plot(), box_plot() |
| hypothesis | Statistical testing | generate_hypotheses(), run_test(), summarize_results() |
| modeling_explain | ML training + SHAP | train(), shap_analysis(), predict(), feature_importance() |

### Shared Schemas (`packages/shared/python/schemas.py`)
13 Pydantic models: TableInfo, ColumnProfile, MergePlan, Recommendation, TargetInfo, Hypothesis, HypothesisResult, Feature, ModelResult, ShapResult, Report, CodeExecutionResult

### Sandbox Security Model
- AST parsing to detect dangerous patterns: `eval`, `exec`, `__import__`, `os.system`, `subprocess.run`, `shutil.rmtree`
- Import allowlist: pandas, numpy, sklearn, matplotlib, plotly, scipy, etc. (30+ modules)
- Subprocess execution with configurable timeout
- All file paths validated to prevent path traversal

## Coding Conventions

### Python (Backend + MCP)
- **Python 3.12+** required
- **Line length:** 100 characters (ruff config)
- **Imports:** `from __future__ import annotations` in files with forward references
- **Naming:** snake_case functions/variables, PascalCase classes
- **Type hints:** Required everywhere. Use `Mapped[]` for SQLAlchemy, Pydantic models for API I/O
- **Async:** All FastAPI endpoints and DB operations are `async def`
- **Linting:** `ruff check` must pass clean before committing
- **Testing:** pytest + pytest-asyncio, SQLite in-memory for unit tests

### TypeScript (Frontend)
- **Strict mode** enabled in tsconfig
- **Path alias:** `@/*` maps to `./src/*`
- **Naming:** camelCase functions/variables, PascalCase components/types/interfaces
- **"use client"** — Only add when component uses hooks, browser APIs, or event handlers
- **Imports:** Individual Lucide icons (`import { Icon } from "lucide-react"`)
- **Styling:** `cn()` utility for conditional Tailwind classes, CVA for component variants
- **No SSR** for Monaco Editor (use `next/dynamic` with `ssr: false`)
- **Type checking:** `tsc --noEmit` must pass clean

### Database
- snake_case table and column names
- UUID primary keys (never auto-increment)
- All timestamps are timezone-aware (`TIMESTAMP(timezone=True)`)
- JSONB for flexible payload columns (trace_events.payload, artifacts.metadata_)
- Cascade deletes on all foreign keys

### Git
- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`
- Don't commit `.env` files (only `.env.example`)
- `package-lock.json` is committed (npm)
- `.claude/` directory is gitignored

## Environment Variables

Required for local development (copy `.env.example` to `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| DATABASE_URL | postgresql+asyncpg://vcengine:vcengine@localhost:5432/vcengine | Async PostgreSQL connection |
| REDIS_URL | redis://localhost:6379/0 | Redis for Arq worker |
| AZURE_OPENAI_API_KEY | (required) | Azure OpenAI API key |
| AZURE_OPENAI_ENDPOINT | (required) | Azure OpenAI endpoint URL |
| AZURE_OPENAI_API_VERSION | 2024-02-01 | API version |
| AZURE_OPENAI_DEPLOYMENT | gpt-4o | Model deployment name |
| UPLOAD_DIR | ./data/uploads | Local file storage path |
| MAX_UPLOAD_SIZE_MB | 500 | Max upload file size |
| CORS_ORIGINS | ["http://localhost:3000"] | Allowed CORS origins |
| NEXT_PUBLIC_API_URL | http://localhost:8000 | API URL for frontend |

## Data Scale Considerations

- **Enterprise scale:** 500MB+ per file, 10M+ rows
- **Chunked reading:** `pd.read_csv(chunksize=50000)` for files >100MB
- **Sampling:** First 100K rows for profiling large files
- **Storage:** Local filesystem with pluggable Azure Blob adapter (future)

## CI/CD Pipeline

GitHub Actions (`.github/workflows/ci.yml`):
1. **Lint Backend** — `ruff check src/` (Python 3.12)
2. **Lint Frontend** — `tsc --noEmit` (Node 20)
3. **Test Backend** — `pytest` with PostgreSQL + Redis services (depends on lint)
4. **Test Frontend** — `vitest run` (depends on lint)

## Important Gotchas

1. **TIMESTAMPTZ is NOT importable** from `sqlalchemy.dialects.postgresql` — use `TIMESTAMP(timezone=True)` from `sqlalchemy` instead
2. **SQLite cannot compile JSONB/UUID** — test conftest.py has compilation hooks to map them (`JSONB→JSON`, `UUID→VARCHAR(36)`)
3. **Monaco Editor requires dynamic import** — will crash SSR if imported normally
4. **SSE endpoint needs special headers** — `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no` (for nginx)
5. **EventService is in-memory** — subscriber queues are lost on restart; clients reconnect via `Last-Event-ID`
6. **Next.js 15 params are async** — page components receive `params` as `Promise<{ sessionId: string }>`, use `useParams()` in client components
7. **Arq worker shares the API image** — same Dockerfile, different entrypoint command
8. **File uploads validate extensions** — only `.csv` and `.xlsx` accepted
9. **aiosqlite required for tests** — listed in dev dependencies, needed for async SQLite test DB
