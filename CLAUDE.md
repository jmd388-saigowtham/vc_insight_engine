# CLAUDE.md — VC Insight Engine

## Project Overview

VC Insight Engine is a production-grade **Autonomous Agentic Data Science Platform** for venture capital firms. It enables AI-orchestrated data science workflows — from data upload through ML modeling and SHAP explainability — with real-time UI tracing, human-in-the-loop approval gates, and a proposal/feedback revision loop.

**Use Case:** VC firms assess data-driven value creation opportunities (churn, expansion, cross-sell, upsell) for portfolio companies.

**Status:** Production-ready. 12 wizard steps, 16 LangGraph agent nodes with hub-and-spoke orchestrator (CoT-SC + ReAct), dual approval systems (code + business proposals), MCP tool integrations, session memory, 471 backend tests, and E2E-verified frontend.

## Architecture

```
[Next.js 15 Frontend] <--SSE/REST--> [FastAPI Backend] <--Arq/Redis--> [Worker]
       (port 3000)                      (port 8000)                       |
                                            |                       [LangGraph Agent]
                                       [PostgreSQL]                  (Hub-and-spoke orchestrator
                                       (port 5432)                   + 16 step nodes)
                                            |                              |
                                      [9 DB Tables]             [10 MCP Tool Servers]
                                                                 (direct Python imports)
                                                                 [Sandbox Executor]
```

## Repository Structure

```
vc-engine/
├── apps/
│   ├── api/           # FastAPI backend (Python 3.12+)
│   │   ├── src/app/   # Application source
│   │   │   ├── agent/       # LangGraph agent (state, graph, 16 nodes, orchestrator, MCP bridge)
│   │   │   │   ├── nodes/         # 16 step nodes + orchestrator + helpers
│   │   │   │   ├── tools/         # MCP bridge
│   │   │   │   ├── state.py       # AgentState TypedDict (30+ fields)
│   │   │   │   ├── graph.py       # Hub-and-spoke StateGraph
│   │   │   │   └── prompts.py     # LLM prompts (including CoT-SC + reflection)
│   │   │   ├── middleware/  # Rate limiting
│   │   │   ├── models/      # SQLAlchemy models (9 tables)
│   │   │   ├── routers/     # FastAPI routers (health, sessions, uploads, profiling, events, code, artifacts, pipeline, proposals)
│   │   │   ├── schemas/     # Pydantic schemas
│   │   │   ├── services/    # Business logic (agent, pipeline, session, events, cleanup, execution_policy, step_state, experiment_tracker, model_registry)
│   │   │   └── worker/      # Arq background tasks
│   │   ├── alembic/   # Database migrations (6 versions)
│   │   └── tests/     # pytest test suite (471 tests)
│   └── web/           # Next.js 15 frontend (Node 20+)
│       └── src/       # Application source
│           ├── app/         # Pages (landing + 12 wizard steps)
│           ├── components/  # UI, wizard, charts, code-modal, live-trace, proposal, feedback
│           ├── hooks/       # React Query + wizard navigation + proposals + feedback hooks
│           ├── stores/      # Zustand stores (session, trace, modal, proposal)
│           ├── lib/         # API client, SSE client, utils
│           └── types/       # TypeScript interfaces
├── packages/
│   ├── mcp-servers/   # 10 Python tool servers (direct import, not HTTP)
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
| Streaming | Server-Sent Events (SSE) with asyncio.Queue pub/sub + historical event loading |
| Code Editor | Monaco Editor (dynamic import, no SSR) |
| Animations | Framer Motion (page transitions) |

## Common Commands

### Backend (apps/api/)
```bash
# Install dependencies
cd apps/api && pip install -e ".[dev]"

# Run API server
cd apps/api && PYTHONPATH=src python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run Arq worker
cd apps/api && python -m arq app.worker.main.WorkerSettings

# Run tests (471 tests)
cd apps/api && PYTHONPATH=src python -m pytest tests/ -x --tb=short

# Lint
cd apps/api && PYTHONPATH=src python -m ruff check src/

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
- **`src/app/main.py`** — FastAPI app factory with lifespan, CORS, structlog, rate limiting middleware, router includes, admin cleanup endpoint
- **`src/app/config.py`** — Pydantic BaseSettings loading from `.env`
- **`src/app/database.py`** — Async SQLAlchemy engine (pool_size=20, max_overflow=10) + `get_db()` generator
- **`src/app/dependencies.py`** — DI providers: `get_settings()`, `get_db_session()`, `get_event_service()`, `get_storage_service()`

### Database Models (`src/app/models/`)
All models inherit from `Base` (DeclarativeBase) and use mixins:
- **`UUIDMixin`** — UUID primary key with `uuid.uuid4` default
- **`TimestampMixin`** — `created_at` with `server_default=func.now()`
- **`FullTimestampMixin`** — adds `updated_at` with `onupdate=func.now()`

**9 tables:** sessions, uploaded_files, column_profiles, trace_events, code_proposals, artifacts, session_context_docs, proposals (business), user_feedback

**Important patterns:**
- Use `Mapped[]` type annotations (SQLAlchemy 2.0 style)
- PostgreSQL-specific types: `UUID(as_uuid=True)`, `JSONB` from `sqlalchemy.dialects.postgresql`
- Use `TIMESTAMP(timezone=True)` for timezone-aware columns — NOT `TIMESTAMPTZ` (not importable)
- All FK relationships use `ondelete="CASCADE"`
- Indexes on `session_id` and `created_at` for all event/file tables

### Pydantic Schemas (`src/app/schemas/`)
- All response schemas use `model_config = ConfigDict(from_attributes=True)` for ORM conversion
- Separate Create/Update/Response models per entity
- Located in: `session.py`, `upload.py`, `profile.py`, `event.py`, `code.py`, `proposal.py`

### Routers (`src/app/routers/`)
| Router | Prefix | Key Endpoints |
|--------|--------|---------------|
| health | `/health` | GET (status + version) |
| sessions | `/sessions` | CRUD + business-context |
| uploads | `/sessions/{id}` | POST /upload (multipart), GET /files |
| profiling | `/files/{id}` | GET /profile, PATCH /columns/{id}/description |
| events | `/sessions/{id}` | GET /events/stream (SSE), GET /events (paginated with dedup IDs) |
| code | `/sessions/{id}` | GET /code/pending, POST /code/{id}/approve\|deny |
| artifacts | `/sessions/{id}` | GET /artifacts, GET /artifacts/{id}/download (with path traversal guard) |
| pipeline | `/sessions/{id}` | GET /target, GET /feature-selection, PATCH /feature-selection, GET /opportunities, POST /start-analysis, POST /resume, POST /feedback, GET /step-states, GET /datasets, POST /select-model, 4 deprecated feedback-shim endpoints |
| proposals | `/proposals` | GET /pending, POST /{id}/approve, POST /{id}/revise, POST /{id}/reject |
| admin | `/admin` | POST /cleanup (delete old files for completed sessions) |

**Pattern:** Each router injects services via `Depends()`. Service instantiation helper at top of file.

### Services (`src/app/services/`)
- **`event_service.py`** — SSE broadcaster using `defaultdict(list)` of `asyncio.Queue` per session. `emit()` writes to DB and broadcasts. `stream()` yields SSE format with 15s keepalive. `get_events()` returns paginated historical events for frontend loading.
- **`profiling_service.py`** — Pandas profiling with chunked reading for files >100MB. Samples first 100K rows. Computes dtypes, null counts, unique counts, min/max/mean, sample values.
- **`upload_service.py`** — File validation (csv/xlsx only), save to disk with UUID name, create DB record.
- **`storage.py`** — Local filesystem adapter using `settings.upload_dir`. Includes `_validate_path()` for path traversal protection.
- **`session_service.py`** — Session CRUD with **step regression guard**: `current_step` can only advance forward, never backwards. Uses `STEP_ORDER` constant.
- **`pipeline_service.py`** — Full data science pipeline: EDA, hypothesis testing, model training, SHAP. `get_opportunities()` only auto-triggers pipeline if no artifacts exist (prevents re-trigger on revisit).
- **`agent_service.py`** — LangGraph runner: builds `AgentState` from DB, invokes `compiled_graph.ainvoke()`, emits SSE events. Handles `submit_feedback()` → `UserFeedback` DB record → merge into `denial_feedback` on resume → `_mark_feedback_consumed()` after completion.
- **`step_state_service.py`** — Tracks per-step states (PENDING, RUNNING, DONE, STALE) with step invalidation cascade.
- **`execution_policy.py`** — Centralized tool execution policy: `is_safe_action()` for read-only tools, `execute_with_policy()` for approval-gated execution, provenance recording. Infrastructure ready for node migration.
- **`experiment_tracker.py`** — Tracks model experiments with metrics, parameters, and artifact paths.
- **`model_registry.py`** — Stores trained model metadata and paths for retrieval.
- **`cleanup_service.py`** — Deletes uploaded files older than 30 days for completed sessions.

### Middleware (`src/app/middleware/`)
- **`rate_limit.py`** — In-memory rate limiter. 100 req/min general, 10 req/min for upload endpoints. Returns 429 when exceeded.

### Agent System (`src/app/agent/`)

#### Hub-and-Spoke Orchestrator Architecture
The agent uses a **hub-and-spoke** pattern with a central `orchestrator_node` that routes to 16 step nodes:
- **`graph.py`** — LangGraph `StateGraph` with orchestrator hub. Every step node returns to orchestrator, which decides next action via LLM.
- **`nodes/orchestrator.py`** — Central routing node with:
  - **CoT-SC (Chain-of-Thought Self-Consistency):** 3 parallel LLM calls at temperatures [0.1, 0.3, 0.5] via `asyncio.gather()`, majority vote on `next_action`, tiebreak by confidence score
  - **Reflection:** After each step completes, runs reflection prompt to assess results vs expectations
  - **Session doc awareness:** Reads completed/pending sections from session doc to inform routing
  - **Fast-path guards:** Skips LLM call when state clearly indicates next step (e.g., no files → profiling)
  - Configurable via `settings.orchestrator_candidate_count` (default 3, set to 1 to disable CoT-SC)

#### State (`state.py`)
`AgentState` TypedDict with 30+ fields: session_id, uploaded_files, column_profiles, merge_plan, target_column, selected_features, eda_results, hypotheses, model_results, explainability_results, recommendations, report_path, error, next_action, current_step, pending_code, approval_status, denial_feedback, denial_count, orchestrator_candidates, orchestrator_reflection, etc.

#### Prompts (`prompts.py`)
LLM prompt templates including `ORCHESTRATOR_COT_SC_PROMPT` (step-by-step reasoning with confidence score) and `ORCHESTRATOR_REFLECTION_PROMPT` (assess last step results).

#### 16 Step Nodes (`nodes/`)
Each is an async function taking/returning AgentState:
- `profiling.py` — Calls `data_ingest.server.profile()` for each uploaded file
- `data_understanding.py` — Deep data analysis and quality assessment
- `dtype_handling.py` — Type inference, casting, and validation. Writes to session doc "Dtype Decisions"
- `merge_planning.py` — Multi-file join detection and execution. Writes to session doc "Merge Strategy"
- `target_id.py` — LLM-assisted target column identification with approval gate
- `preprocessing.py` — Missing value handling + categorical encoding with ReAct validation
- `feature_eng.py` — Scaling, polynomial features, interaction features with ReAct validation
- `feature_selection.py` — Feature importance ranking and selection
- `eda.py` — Distribution, correlation, target analysis, box plots
- `hypothesis.py` — Statistical hypothesis generation and testing with ReAct validation
- `opportunity_analysis.py` — Value creation opportunity identification
- `modeling.py` — ML model training (logistic regression, random forest, gradient boosting) with ReAct validation
- `threshold_calibration.py` — Classification threshold tuning. Writes to session doc "Threshold Decisions"
- `explainability.py` — SHAP analysis on best model with ReAct validation
- `recommendation.py` — VC-focused recommendation generation from results
- `report.py` — Executive summary compilation

#### Node Helpers (`nodes/node_helpers.py`)
Shared utilities for all nodes:
- `read_step_context(state, step)` — Reads session doc section + denial feedback + dependent sections via `STEP_CONTEXT_DEPENDENCIES` mapping (11 steps mapped to their dependent doc sections)
- `emit_trace(state, event_type, step, payload)` — Emits trace events to SSE
- `invoke_llm_json(prompt, temperature)` — Calls Azure OpenAI and parses JSON response
- `react_execute(state, step, action_fn, validate_fn, max_retries=3)` — ReAct loop: think → act → observe → reflect → retry/escalate
- `execute_via_policy(state, step, server, tool, args, description)` — Centralized execution via ExecutionPolicyService (infrastructure ready, not yet called by nodes)
- `record_step_provenance(state, step, code, stdout, stderr, artifacts)` — Records execution provenance

#### Approval Helpers (`nodes/approval_helpers.py`)
Two-phase approval gate with self-heal:
1. **Propose:** Node generates code, sets `pending_*` fields, returns `next_action="wait"`
2. **Execute/Deny:** On resume, checks `approval_status` — approved triggers execution, denied triggers self-heal
3. **Self-heal:** On denial (up to `MAX_DENIALS=2`), cycles through alternative strategies

#### MCP Bridge (`tools/mcp_bridge.py`)
Direct Python import bridge with lazy-loading `_SERVER_LOADERS` registry. Dispatches `call_tool(server_name, tool_name, args)` to the correct MCP server function.

### Worker (`src/app/worker/`)
- **`main.py`** — Arq WorkerSettings with Redis connection, max_jobs=10, job_timeout=600s
- **`tasks.py`** — `run_step()` task that creates DB session + EventService, invokes `AgentService` with compiled graph

### Testing (471 tests)
- **conftest.py** — Uses SQLite+aiosqlite for tests with compilation hooks mapping `JSONB→JSON` and `UUID→VARCHAR(36)` for SQLite compatibility
- Override `get_db_session` dependency with test session factory
- Uses `httpx.AsyncClient` with `ASGITransport` for endpoint testing
- **Test files** cover: health, sessions, uploads, profiling, events, artifacts, code proposals, session service, pipeline, orchestrator (CoT-SC, reflection, fast-path), proposals, feedback, execution policy, experiment tracker, model registry, dtype handling, feature enforcement, threshold calibration, stale propagation, session memory, trace completeness, agent proposals, code provenance, custom endpoints, and more

## Frontend Architecture

### App Router Structure (`src/app/`)
- **Root layout** (`layout.tsx`) — ThemeProvider (next-themes), QueryClientProvider, Toaster (sonner)
- **Landing page** (`page.tsx`) — Hero section + "Start New Analysis" button + **Recent Analyses** session history grid (uses `useSessions()` hook, shows company name, industry, status badge, current step, relative date; click navigates to session's current step)
- **`sessions/new/`** — Creates session via mutation, redirects to onboarding
- **`sessions/[sessionId]/layout.tsx`** — Wizard layout with session context, **Framer Motion page transitions** (AnimatePresence + motion.div fade/slide-up), **ErrorBoundary** wrapper
- **12 wizard pages** under `[sessionId]/`: onboarding, upload, profiling, workspace, target, feature-selection, eda, hypotheses, hypothesis-results, models, shap, report

### Wizard Navigation System
The wizard uses a **high water mark** pattern for step navigation:
- **`highWaterStep`** (from DB `session.current_step`) — the furthest step the user has reached
- **`currentStep`** (from URL) — the step currently being viewed
- Steps up to `highWaterStep` are clickable (completed or current). Steps beyond are locked.
- Users can freely navigate back to any completed step without losing progress.

**`useWizardNavigation(currentUrlStep)`** hook (`hooks/use-wizard-navigation.ts`):
- **At the frontier** (URL step >= DB step): Continue button advances `current_step` in DB (with optional `extraData` like `target_column`), then navigates
- **Reviewing past step** (URL step < DB step): If `extraData` provided, sends PATCH without advancing step; otherwise just navigates
- Prevents step regression — you can't accidentally go backwards in the pipeline

### SSE Event System with Historical Loading
**`useEventStream`** hook (`hooks/use-events.ts`):
1. On mount, fetches historical events via `GET /sessions/{id}/events?limit=200`
2. Reverses from DESC to chronological, calls `setEvents()` to populate store
3. Builds a `Set<string>` of known event IDs for deduplication
4. Opens SSE connection; `onEvent` skips any events already in the set
5. This ensures trace events **persist across page navigation** — no more lost events

### Dual Approval Systems
The platform has **two distinct approval flows**:

1. **Code Proposals** (technical, code-level):
   - **Modal:** `CodeApprovalModal` (`components/code-modal/`) with Monaco editor
   - **Endpoints:** `POST /code/{id}/approve`, `POST /code/{id}/deny`
   - **Trigger:** SSE event `CODE_PROPOSED` auto-opens modal
   - **Store:** `modalStore` (`stores/modal-store.ts`)

2. **Business Proposals** (strategic, plan-level):
   - **Component:** `PendingProposals` + `ProposalCard` (`components/proposal/`)
   - **Endpoints:** `POST /proposals/{id}/approve`, `POST /proposals/{id}/revise`, `POST /proposals/{id}/reject`
   - **Trigger:** SSE event `PROPOSAL_CREATED` auto-opens proposal panel
   - **Store:** `proposalStore` (`stores/proposal-store.ts`)

### Feedback System
**`FeedbackInput`** component (`components/feedback/feedback-input.tsx`):
- Expandable panel at bottom of wizard pages with Live Trace sidebar
- Detects pending proposals for current step — when present, feedback is routed as a revision
- When no pending proposal, submits generic feedback via `POST /sessions/{id}/feedback`
- Shows recent feedback history with status (pending/consumed)

### Component Patterns
- **UI components** (`components/ui/`) — Follow shadcn/ui pattern: `cn()` utility, `forwardRef`, CVA for variants. All use Radix primitives.
- **"use client"** directive — ONLY on components using hooks, browser APIs, or interactivity. Server components are default.
- **Dynamic imports** — Monaco Editor loaded via `next/dynamic` with `ssr: false`

### Key Components
| Component | Location | Purpose |
|-----------|----------|---------|
| WizardNav | `components/wizard/wizard-nav.tsx` | 12-step horizontal stepper with high water mark logic + theme toggle |
| WizardLayout | `components/wizard/wizard-layout.tsx` | Layout wrapper accepting `highWaterStep` prop |
| LiveTraceSidebar | `components/live-trace/live-trace-sidebar.tsx` | Collapsible right sidebar, SSE-connected event list with historical loading |
| TraceEventItem | `components/live-trace/trace-event-item.tsx` | Color-coded event display with expandable JSON |
| CodeApprovalModal | `components/code-modal/code-approval-modal.tsx` | Monaco editor + approve/deny/edit buttons (code-level proposals) |
| PendingProposals | `components/proposal/pending-proposals.tsx` | Lists pending business proposals for a step |
| ProposalCard | `components/proposal/proposal-card.tsx` | Approve/revise/reject UI for business proposals |
| FeedbackInput | `components/feedback/feedback-input.tsx` | Expandable AI feedback panel with revision wiring |
| Dropzone | `components/upload/dropzone.tsx` | react-dropzone wrapper with progress |
| ChartGrid | `components/charts/chart-grid.tsx` | Responsive grid of artifact images with loading skeletons |
| ErrorBoundary | `components/error-boundary.tsx` | React error boundary with retry button |
| ThemeToggle | `components/theme-toggle.tsx` | Sun/Moon dark/light mode toggle |

### State Management
| Store | File | State |
|-------|------|-------|
| sessionStore | `stores/session-store.ts` | currentSessionId, session object |
| traceStore | `stores/trace-store.ts` | events[], isConnected boolean, setEvents() for bulk load |
| modalStore | `stores/modal-store.ts` | isOpen, proposal (CodeProposal) for code approval modal |
| proposalStore | `stores/proposal-store.ts` | isOpen, proposal (BusinessProposal) for business proposal panel |

### Hooks (TanStack Query)
| Hook | File | Operations |
|------|------|-----------|
| useSession | `hooks/use-session.ts` | GET session, create mutation, update mutation |
| useSessions | `hooks/use-session.ts` | GET all sessions (for landing page history) |
| useTables | `hooks/use-tables.ts` | GET tables/profiles, upload mutation, update column desc |
| useArtifacts | `hooks/use-artifacts.ts` | GET artifacts by session |
| useEventStream | `hooks/use-events.ts` | Historical load + SSE connection with dedup, pushes to traceStore |
| useWizardNavigation | `hooks/use-wizard-navigation.ts` | Frontier-aware step navigation with extraData support |
| useProposals | `hooks/use-proposals.ts` | GET pending proposals, approve/revise/reject mutations |
| useFeedback | `hooks/use-feedback.ts` | POST feedback, GET recent feedback |

**Query key pattern:** `["entity", id]` e.g. `["session", sessionId]`, `["proposals", "pending", sessionId]`

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
- **`session.ts`** — Session (with target_column, selected_features, step_states), SessionCreate interfaces
- **`event.ts`** — TraceEvent, EventType union type (16+ event types including PROPOSAL_CREATED, PROPOSAL_APPROVED, AI_REASONING, STEP_STALE)
- **`api.ts`** — UploadedFile, ColumnProfile, CodeProposal, CodeContext, BusinessProposal, Artifact, Hypothesis, ModelResult, ShapResult, Report

## MCP Tool Servers (packages/mcp-servers/)

Direct Python function calls with Pydantic I/O schemas (not stdio MCP servers). Each tool is a module under `src/` with `__init__.py` + `server.py`. Called by agent nodes via `mcp_bridge.py` using direct Python imports.

| Tool | Purpose | Key Functions |
|------|---------|---------------|
| session_doc | Session context persistence (20 mandatory sections) | initialize(), read(), upsert(), upsert_structured(), get_section() |
| data_ingest | Data profiling & sampling | profile(), sample(), row_count(), list_sheets() |
| dtype_manager | Type casting & validation | cast_column(), validate_types(), suggest_types() |
| merge_planner | Table join detection | detect_keys(), generate_merge_code(), execute_merge() |
| code_registry | Code snippet storage | store(), retrieve(), get_latest() |
| sandbox_executor | Safe code execution | run(), validate_code() — AST analysis + subprocess + network blocking |
| preprocessing | Data cleaning | handle_missing(), encode_categorical(), scale_numeric(), create_polynomial_features(), create_interaction_features() |
| eda_plots | Chart generation | distribution_plot(), correlation_matrix(), scatter_plot(), box_plot(), target_analysis() |
| hypothesis | Statistical testing | generate_hypotheses(), run_test(), summarize_results() |
| modeling_explain | ML training + SHAP | train(), shap_analysis(), predict(), feature_importance(), detect_leakage() |

### Session Doc (20 Mandatory Sections)
The session_doc MCP server maintains a structured JSON document per session with 20 sections: Data Inventory, Dtype Decisions, Merge Strategy, Target Variable, Feature Selection, Preprocessing Decisions, EDA Findings, Hypotheses & Results, Model Results, Explainability, Recommendations, Trained Model Paths, Generated Code Paths, Threshold Decisions, and more. Initialized in `agent_service._build_initial_state()`.

### Shared Schemas (`packages/shared/python/schemas.py`)
13 Pydantic models: TableInfo, ColumnProfile, MergePlan, Recommendation, TargetInfo, Hypothesis, HypothesisResult, Feature, ModelResult, ShapResult, Report, CodeExecutionResult

### Sandbox Security Model
- AST parsing to detect dangerous patterns: `eval`, `exec`, `__import__`, `os.system`, `subprocess.run`, `shutil.rmtree`
- Import allowlist: pandas, numpy, sklearn, matplotlib, plotly, scipy, etc. (30+ modules)
- **Network import blocklist**: socket, http, urllib, requests, httpx, aiohttp, ftplib, smtplib, xmlrpc, ssl, websocket
- **Proxy env stripping**: HTTP_PROXY, HTTPS_PROXY, etc. removed from subprocess environment
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
- **Next.js typed routes:** Use `as never` cast on `router.push()` for dynamic route strings

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
| AZURE_OPENAI_API_VERSION | 2024-12-01-preview | API version |
| AZURE_OPENAI_DEPLOYMENT | gpt-4o | Model deployment name |
| UPLOAD_DIR | ./data/uploads | Local file storage path |
| MAX_UPLOAD_SIZE_MB | 500 | Max upload file size |
| CORS_ORIGINS | ["http://localhost:3000", "http://localhost:3001"] | Allowed CORS origins |
| NEXT_PUBLIC_API_URL | http://localhost:8000 | API URL for frontend |

## Key Design Patterns

### Hub-and-Spoke Orchestrator with CoT-SC
The LangGraph agent uses a central orchestrator node that routes to 16 step nodes. The orchestrator uses Chain-of-Thought Self-Consistency: 3 parallel LLM calls at different temperatures, majority vote on next action, with reflection after each completed step.

### ReAct Loop for Critical Execution
Critical execution nodes (modeling, preprocessing, hypothesis, explainability, feature_eng) use a ReAct pattern: think → act → observe → reflect → retry/escalate (up to 3 attempts before requesting user input).

### High Water Mark Wizard Navigation
The wizard tracks two separate concepts:
- **`currentStep`** (URL) — which page the user is currently viewing
- **`highWaterStep`** (DB `session.current_step`) — the furthest step ever reached
- Navigation is free for all completed steps; locked for steps beyond the high water mark
- Continue buttons only mutate DB when at the frontier (URL step >= DB step)
- `navigateToNext(nextStep, extraData?)` supports passing additional fields (e.g., `target_column`) alongside step advancement
- Backend enforces this too: `session_service.py` rejects step regressions

### Pipeline Auto-Trigger Guard
`pipeline_service.py:get_opportunities()` checks artifact count before running pipeline. If artifacts already exist for the session, the pipeline is NOT re-triggered. This prevents duplicate execution when users revisit the workspace page.

### MCP Bridge (Direct Import)
Agent nodes call MCP servers via `mcp_bridge.py` which uses a lazy-loading registry pattern. No HTTP calls — functions are imported directly from `packages/mcp-servers/src/{server_name}/server.py`.

### Two-Phase Approval Gate with Self-Heal
Code-generating nodes follow a two-phase pattern (`approval_helpers.py`):
1. **Propose:** Node generates code description, sets `pending_*` fields, returns with `next_action="wait"`
2. **Execute/Deny:** On resume, node checks `approval_status` — approved triggers execution, denied triggers self-heal
3. **Self-heal:** On denial (up to `MAX_DENIALS=2`), nodes cycle through alternative strategies

### Dual Approval Systems
- **Code proposals** (`CodeApprovalModal`): For code-level approvals via `/code/{id}/approve|deny`
- **Business proposals** (`PendingProposals` + `ProposalCard`): For strategic plan-level approvals via `/proposals/{id}/approve|revise|reject`
- These are **separate systems** — do not confuse them or remove one thinking it duplicates the other

### Session Memory as Source of Truth
The `session_doc` MCP server maintains a 20-section structured document per session. Nodes read context via `read_step_context()` which pulls the relevant section + `STEP_CONTEXT_DEPENDENCIES` (dependent sections from upstream steps). Nodes write back via `upsert_structured()`. The orchestrator checks completed/pending sections to inform routing.

### Feedback → Revision Loop
User feedback flows: `POST /sessions/{id}/feedback` → `UserFeedback` DB record → on `resume()`, merged into `denial_feedback` → nodes read feedback to adjust behavior → `_mark_feedback_consumed()` after completion.

### Deprecated Endpoints as Feedback Shims
Four legacy endpoints now route through the agent proposal flow instead of direct execution:
- `POST /sessions/{id}/train-additional-model` → feedback with step="modeling"
- `POST /sessions/{id}/eda/custom-plot` → feedback with step="eda"
- `POST /sessions/{id}/hypotheses/custom` → feedback with step="hypothesis"
- `POST /sessions/{id}/retrain-threshold` → feedback with step="threshold_calibration"
All return `{"status": "feedback_submitted", "message": "Request routed through AI agent proposal flow"}`.

### ML Pipeline Capabilities
- **3-way split:** 70% train / 15% validation / 15% test with stratified sampling
- **Hyperparameter tuning:** `RandomizedSearchCV` with 3-fold CV, up to 10 iterations
- **Overfit/underfit detection:** Compares train vs test metrics; reports `good_fit`, `overfitting`, or `underfitting` with diagnostic messages
- **Target leakage detection:** `detect_leakage()` checks feature-target correlations above threshold (default 0.95)
- **Class imbalance handling:** Auto-detects minority ratio < 0.2 and applies `class_weight="balanced"`
- **Time-aware split:** `split_strategy="auto"` detects date columns and uses chronological split for time-series data
- **Feature engineering:** Polynomial features (degree-N), pairwise interaction features, multiple scaling methods
- **Multi-sheet xlsx:** `list_sheets()` enumerates sheets; `profile()` and `sample()` accept `sheet_name` parameter
- **Many-to-many join warnings:** `execute_merge()` detects duplicate keys on both sides and warns about row explosion risk

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
5. **EventService is in-memory** — subscriber queues are lost on restart; clients reconnect via `Last-Event-ID`; historical events loaded via REST on mount
6. **Next.js 15 params are async** — page components receive `params` as `Promise<{ sessionId: string }>`, use `useParams()` in client components
7. **Arq worker shares the API image** — same Dockerfile, different entrypoint command
8. **File uploads validate extensions** — only `.csv` and `.xlsx` accepted
9. **aiosqlite required for tests** — listed in dev dependencies, needed for async SQLite test DB
10. **Next.js typed routes** — Dynamic route strings in `router.push()` need `as never` cast to satisfy strict type checking
11. **Don't use Radix Collapsible inside `<tbody>`** — Collapsible renders a `<div>` wrapper, which is invalid inside `<tbody>`. Use plain `useState` + conditional `{open && <tr>}` rendering instead.
12. **CORS includes port 3001** — When port 3000 is in use, Next.js auto-selects 3001. Both ports are in the CORS allowlist.
13. **Step regression is blocked at two levels** — Frontend (`useWizardNavigation`) skips DB mutation when reviewing past steps. Backend (`session_service.py`) silently drops `current_step` updates that would go backwards.
14. **Pipeline only runs once per session** — `get_opportunities()` checks artifact count before auto-triggering `run_pipeline()`. Revisiting workspace does NOT re-run the pipeline.
15. **Rate limiting is in-memory** — Resets on server restart. 100 req/min general, 10 req/min for uploads.
16. **Target column must be passed via `extraData`** — The target page must call `navigateToNext("feature-selection", { target_column: config?.target_variable })` to persist the target column to the session DB. Without this, the feature-selection page shows a "no target" warning.
17. **Two approval systems are NOT duplicates** — `CodeApprovalModal` (code router: `/code/{id}/approve|deny`) and `PendingProposals` (proposals router: `/proposals/{id}/approve|revise|reject`) serve different purposes. Do not delete one thinking it replaces the other.
18. **Deprecated endpoints are feedback shims** — The 4 legacy action endpoints (train-additional-model, custom-plot, hypotheses/custom, retrain-threshold) now route through `AgentService.submit_feedback()`. They return `"status": "feedback_submitted"` — NOT direct execution results.
19. **`execute_via_policy()` is defined but unused** — The centralized execution policy helper exists in `node_helpers.py` but no node calls it yet. This is intentional infrastructure for incremental migration (Phase 12).
20. **SSE events use UUID-based dedup** — `use-events.ts` builds a `Set<string>` of event IDs from historical fetch and skips SSE events already in the set. Do NOT re-add `clearEvents()` on mount — it was intentionally removed.
21. **Server restart needed for code changes** — If running without `--reload`, code changes (especially in routers/services) won't take effect until server restart. Always use `--reload` during development.
22. **MCP imports require `nodes/__init__.py` sys.path setup** — All agent node files that import MCP server modules (e.g., `from merge_planner.server import ...`) depend on `sys.path` being configured in `apps/api/src/app/agent/nodes/__init__.py`. If you add a new node or MCP server import, the path setup in `__init__.py` must run first. Do NOT rely on `node_helpers.py` alone — it may not be imported early enough.
23. **Resume endpoint needs proposal_id** — `POST /sessions/{id}/resume` must include `proposal_id` and `proposal_type: "business"` when resuming after a business proposal approval. Without these, `_build_initial_state()` builds fresh state that doesn't carry the approval forward, causing the agent to loop on the same step.
