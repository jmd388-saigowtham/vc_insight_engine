# Architecture

## System Overview

VC Insight Engine is an autonomous agentic data science platform for venture capital firms. It orchestrates end-to-end ML workflows — from data upload through modeling and SHAP explainability — using a LangGraph agent with human-in-the-loop code approval, real-time SSE streaming, and a 12-step wizard UI.

```
Browser (Next.js 15, port 3000)
    |
    | REST + SSE
    v
FastAPI (port 8000) -----> PostgreSQL 16 (port 5432)
    |                        7 tables, JSONB, UUID PKs
    |
    v
Redis 7 (port 6379)
    |
    v
Arq Worker (async, max 10 jobs)
    |
    v
LangGraph Agent (hub-and-spoke orchestrator)
    |
    v
10 MCP Tool Servers (direct Python imports)
    |
    v
Sandbox Executor (subprocess isolation)
```

## Components

| Component | Technology | Role |
|-----------|-----------|------|
| **Frontend** | Next.js 15 App Router, React 19, Tailwind, Radix UI | 12-step wizard UI, SSE event stream, code approval modal |
| **API** | FastAPI, async SQLAlchemy 2.0, Pydantic v2, structlog | REST endpoints, SSE streaming, file handling, rate limiting |
| **Worker** | Arq (Redis-backed async) | Background agent execution, 600s job timeout |
| **Database** | PostgreSQL 16 | Sessions, uploads, profiles, events, code proposals, artifacts |
| **Cache/Queue** | Redis 7 | Arq task queue |
| **Agent** | LangGraph state machine, Azure OpenAI (GPT-4o) | Hub-and-spoke orchestrator with 12 execution nodes |
| **MCP Servers** | 10 Python tool modules | Data profiling, preprocessing, EDA, hypothesis testing, ML, SHAP |

## Key Architectural Patterns

### Hub-and-Spoke LangGraph Orchestrator

The agent uses a hub-and-spoke architecture, not a linear pipeline. A central **orchestrator node** is the entry point and decision hub:

1. The orchestrator examines current step states, session context, and errors.
2. It uses a **heuristic fast-path** (dependency graph traversal) when the next step is obvious.
3. It falls back to **LLM reasoning** (Azure OpenAI) for ambiguous situations — errors, retries, multiple ready steps.
4. It sets `next_action` in the agent state, which the graph router dispatches to the appropriate execution node.
5. Every execution node returns to the orchestrator, which decides what to do next.

Valid actions: any of the 12 execution node names, `wait` (pending approval), or `end`.

### Step State Machine

Each pipeline step has a state tracked in the session's `step_states` JSONB column:

```
NOT_STARTED --> READY --> RUNNING --> DONE
                  ^                    |
                  |                    v (if upstream re-run)
                READY <--- STALE <----+
                  |
                  v
               FAILED
```

States: `NOT_STARTED`, `READY`, `RUNNING`, `DONE`, `STALE`, `FAILED`.

A **dependency graph** defines prerequisites for each step. Steps become `READY` only when all dependencies are `DONE`.

### Step Invalidation and Rerun

When a user edits data at an earlier step and triggers a rerun:

1. The `StepStateService.invalidate_downstream()` method performs a BFS through the reverse dependency graph.
2. All downstream `DONE` or `RUNNING` steps are marked `STALE`.
3. The target step is marked `READY`.
4. `STEP_STALE` events are emitted via SSE so the UI can update badges.
5. The agent re-executes from the target step, respecting the dependency graph.

### Human-in-the-Loop Code Approval

When the agent generates code for execution:

1. A `CodeProposal` record is created with status `pending`.
2. A `CODE_PROPOSED` event is emitted via SSE.
3. The orchestrator sets `next_action = "wait"`, pausing the pipeline.
4. The user reviews code in a Monaco editor modal and approves or denies.
5. On approval, the frontend calls `/code/{id}/approve` and then `/sessions/{id}/resume`.
6. The orchestrator resumes and continues the pipeline.

### High Water Mark Wizard Navigation

The frontend wizard tracks two concepts:

- **`highWaterStep`** (DB `session.current_step`) — the furthest step ever reached.
- **`currentStep`** (from URL) — the step currently being viewed.

Users can freely navigate back to completed steps. The Continue button only mutates the DB when at the frontier (URL step >= DB step). The backend enforces this too — step regressions are silently dropped.

### SSE Real-Time Streaming

The `EventService` uses an in-memory `defaultdict(list)` of `asyncio.Queue` instances per session. When an event is emitted:

1. It is persisted to the `trace_events` table.
2. It is broadcast to all connected SSE subscribers for that session.
3. The SSE endpoint sends 15-second keepalive pings.
4. Clients reconnect via `Last-Event-ID` header for resumption.

### Session Context Doc

The `session_doc` MCP server maintains a single markdown document per session that serves as the agent's memory. Each node reads/writes sections of this document to maintain context across steps.

### MCP Bridge (Direct Import)

MCP tool servers are plain Python modules, not HTTP or stdio servers. The `MCPBridge` class uses a lazy-loading registry (`_SERVER_LOADERS`) that imports functions on first use and caches them. Agent nodes call `bridge.call_tool("server_name", "function_name", args)`.

10 registered servers: `data_ingest`, `merge_planner`, `preprocessing`, `sandbox_executor`, `eda_plots`, `hypothesis`, `modeling_explain`, `session_doc`, `dtype_manager`, `code_registry`.

## 12-Step Wizard

| # | UI Step | Pipeline Node | Purpose |
|---|---------|---------------|---------|
| 1 | onboarding | — | Company name, industry, business context |
| 2 | upload | — | CSV/XLSX file upload with auto-profiling |
| 3 | profiling | profiling | Column-level statistics, data types, distributions |
| 4 | workspace | merge_planning | Multi-file merge detection and execution |
| 5 | target | target_id | Target variable identification (heuristic + binary detection) |
| 6 | feature-selection | feature_selection | User selects/deselects features for modeling |
| 7 | eda | eda | Distribution, correlation, target analysis, box plots |
| 8 | hypotheses | hypothesis | Statistical hypothesis generation and testing |
| 9 | hypothesis-results | — | Review hypothesis test results |
| 10 | models | modeling | Train logistic regression, random forest, gradient boosting |
| 11 | shap | explainability | SHAP waterfall and force plots on best model |
| 12 | report | recommendation + report | VC-focused recommendations + executive summary |

### Pipeline Dependency Graph

```
profiling
    └── merge_planning
            └── target_id
                    ├── feature_selection
                    │       ├── eda
                    │       └── preprocessing
                    │               ├── hypothesis (also depends on eda)
                    │               └── feature_eng
                    │                       └── modeling (also depends on hypothesis)
                    │                               └── explainability
                    │                                       └── recommendation
                    │                                               └── report
```

## Data Flow

1. **Upload** — User uploads CSV/Excel files. Files stored on disk with UUID names; metadata and auto-profiling results saved to PostgreSQL.
2. **Profile** — Column-level statistics computed: dtypes, null counts, unique counts, min/max/mean, sample values. Large files (>100MB) are chunked and sampled (first 100K rows).
3. **Merge** — For multi-file sessions, the merge planner detects join keys and executes merges.
4. **Target ID** — Heuristic identification of the target column (common churn/outcome names + binary detection).
5. **Feature Selection** — User reviews and selects features. Target column is excluded.
6. **EDA** — Automated chart generation: distributions, correlations, target analysis, box plots. Saved as artifact images.
7. **Preprocessing** — Handle missing values, encode categoricals, scale numerics.
8. **Hypothesis Testing** — Generate and test statistical hypotheses (t-test, chi-square, correlation).
9. **Modeling** — Train multiple classifiers (logistic regression, random forest, gradient boosting). Best model selected by AUC-ROC.
10. **Explainability** — SHAP analysis on the best model. Waterfall and force plots saved as artifacts.
11. **Recommendations** — VC-focused recommendations generated from model results and SHAP.
12. **Report** — Executive summary compiled: key findings, recommendations, model summary.

## Directory Structure

```
vc-engine/
├── apps/
│   ├── api/                 # FastAPI backend (Python 3.12+)
│   │   ├── src/app/
│   │   │   ├── agent/       # LangGraph agent (state, graph, orchestrator, 12 nodes, MCP bridge)
│   │   │   ├── middleware/  # Rate limiting
│   │   │   ├── models/      # SQLAlchemy models (7 tables)
│   │   │   ├── routers/     # FastAPI routers (8 modules)
│   │   │   ├── schemas/     # Pydantic schemas
│   │   │   ├── services/    # Business logic (pipeline, session, events, step states, cleanup)
│   │   │   └── worker/      # Arq background tasks
│   │   ├── alembic/         # Database migrations
│   │   └── tests/           # pytest suite
│   └── web/                 # Next.js 15 frontend (Node 20+)
│       └── src/
│           ├── app/         # Pages (landing + 12 wizard steps)
│           ├── components/  # UI, wizard, charts, code modal, live trace
│           ├── hooks/       # React Query + wizard navigation hooks
│           ├── stores/      # Zustand stores
│           ├── lib/         # API client, SSE client, utils
│           └── types/       # TypeScript interfaces
├── packages/
│   ├── mcp-servers/         # 10 Python tool servers (direct import)
│   └── shared/              # Shared Pydantic schemas
├── infra/                   # Docker Compose, nginx, init.sql
└── docs/                    # Documentation
```
