# VC Insight Engine — Project Status & Capability Report

**Last Updated:** 2026-03-08
**Overall Status:** Feature-complete with LLM-driven orchestration, two-phase approval with self-heal, report exports, and comprehensive test suite

---

## Table of Contents

1. [What Is This Project?](#what-is-this-project)
2. [What Has Been Implemented](#what-has-been-implemented)
3. [Is AI Included?](#is-ai-included)
4. [Detailed Capabilities — What It CAN Do](#detailed-capabilities--what-it-can-do)
5. [Limitations — What It CANNOT Do](#limitations--what-it-cannot-do)
6. [How It Works — Technical Deep Dive](#how-it-works--technical-deep-dive)
7. [Implementation Status Table](#implementation-status-table)

---

## What Is This Project?

VC Insight Engine is a **full-stack autonomous data science platform** built for venture capital firms. A VC analyst uploads a portfolio company's data (customer data, transaction data, etc.), and the system automatically:

1. Profiles the data (column types, nulls, distributions)
2. Merges multiple tables if needed
3. Identifies the target variable (e.g., churn)
4. Generates exploratory data analysis (EDA) charts
5. Runs statistical hypothesis tests
6. Trains machine learning models (Logistic Regression, Random Forest, Gradient Boosting)
7. Produces SHAP explainability analysis
8. Generates VC-focused recommendations (churn prevention, cross-sell, upsell)
9. Compiles an executive report with key findings

All of this happens through an 11-step wizard UI with real-time progress tracking via Server-Sent Events (SSE).

---

## What Has Been Implemented

### Frontend (Next.js 15 + React 19) — 100% Complete

| Feature | Status | Details |
|---------|--------|---------|
| Landing page with session history | Done | Shows all past sessions with company name, industry, status badge, relative date. Click to resume. |
| 11-step wizard navigation | Done | High water mark pattern — freely navigate completed steps, locked for future steps |
| Onboarding page | Done | Company name, industry, business context form |
| File upload with progress | Done | Drag-and-drop CSV/XLSX upload with XHR progress bar |
| Data profiling view | Done | Column-level stats (nulls, unique counts, dtypes, min/max/mean, samples) |
| Workspace / opportunities | Done | AI-detected value creation opportunities (churn, expansion, cross-sell, upsell) |
| Target variable selection | Done | Auto-detected target with manual override |
| EDA charts | Done | Displays generated charts (distribution, correlation, missing values, feature distributions) |
| Hypothesis testing results | Done | Table with test statistic, p-value, supported/rejected badge, expandable conclusions |
| Model leaderboard | Done | Ranked by F1 score with accuracy/precision/recall/AUC-ROC, expandable confusion matrix, threshold tuning slider |
| SHAP explainability | Done | Feature importance bar chart + summary plot |
| Feature selection page | Done | Select/deselect features before modeling, filter target from features |
| Executive report | Done | Summary, key findings, recommendations, export buttons (PDF/PPTX/CSV) |
| Live trace sidebar | Done | Real-time SSE event stream showing pipeline progress |
| Code approval modal | Done | Monaco editor for reviewing/approving/denying generated code |
| Dark/light theme toggle | Done | Sun/Moon toggle using next-themes |
| Page transitions | Done | Framer Motion fade/slide animations between wizard steps |
| Error boundary | Done | Catches rendering errors with retry button |
| Loading skeletons | Done | Proper skeleton states for workspace, EDA, models pages |

### Backend (FastAPI + Python) — 100% Complete

| Feature | Status | Details |
|---------|--------|---------|
| Session CRUD | Done | Create, read, update, list sessions with pagination |
| File upload & storage | Done | CSV/XLSX validation, UUID naming, size limits (500MB) |
| Column profiling | Done | Pandas-based profiling with chunked reading for large files (>100MB) |
| SSE event streaming | Done | Real-time event broadcasting with in-memory pub/sub, auto-reconnect |
| Code proposal system | Done | Create, approve, deny code proposals with status tracking |
| Artifact management | Done | CRUD for generated artifacts (charts, reports), download with path traversal protection |
| Pipeline service | Done | Monolithic data science pipeline (EDA, hypothesis, modeling, SHAP) |
| Two-phase approval gate | Done | Code-generating nodes propose code, wait for approval, self-heal on denial (up to 3 retries with alternative strategies) |
| Step state service | Done | DAG-based step states with dependency graph, invalidation, and go-back-and-edit support |
| Custom analysis endpoints | Done | `select-model`, `train-additional`, `custom-plot`, `custom-hypothesis`, `retrain-threshold` |
| Report export (PDF/CSV) | Done | `GET /sessions/{id}/report/pdf` (ReportLab) and `GET /sessions/{id}/report/csv` |
| Step regression guard | Done | Backend prevents `current_step` from ever going backwards |
| Pipeline auto-trigger guard | Done | `get_opportunities()` only runs pipeline on first visit (checks artifact count) |
| Rate limiting | Done | In-memory middleware: 100 req/min general, 10 req/min uploads |
| File cleanup | Done | Service to delete files older than 30 days for completed sessions |
| Path traversal protection | Done | `_validate_path()` in storage service ensures files stay within upload directory |
| CORS configuration | Done | Configurable origins, includes both port 3000 and 3001 |

### LangGraph Agent System — 100% Complete (LLM-Driven)

| Component | Status | Details |
|-----------|--------|---------|
| Agent state (TypedDict) | Done | 30+ fields covering full pipeline lifecycle, approval gates, denial tracking |
| Graph definition | Done | Hub-and-spoke architecture: orchestrator dispatches to 12 execution nodes |
| Orchestrator node | Done | LLM-first routing hub (Azure OpenAI GPT-4o) with fast-path guard and fallback heuristic |
| MCP bridge | Done | Direct Python import bridge with lazy-loading for all 10 MCP servers |
| Profiling node | Done | Calls `data_ingest.server.profile()` |
| Merge planning node | Done | Calls `merge_planner.server.detect_keys()` + `execute_merge()` |
| Target identification node | Done | Heuristic target column detection |
| Feature selection node | Done | User-driven feature selection with validation |
| EDA node | Done | Calls `eda_plots.server` for 4 chart types |
| Preprocessing node | Done | Calls `preprocessing.server.handle_missing()` + `encode_categorical()` |
| Hypothesis node | Done | Calls `hypothesis.server.generate_hypotheses()` + `run_test()` |
| Feature engineering node | Done | Calls `preprocessing.server.scale_numeric()`, polynomial/interaction features |
| Modeling node | Done | Calls `modeling_explain.server.train()` for 3+ model types |
| Explainability node | Done | Calls `modeling_explain.server.shap_analysis()` |
| Recommendation node | Done | LLM-enhanced VC-focused recommendations |
| Report node | Done | LLM-enhanced executive summary + key findings + recommendations |
| Agent service | Done | Invokes `compiled_graph.ainvoke()` with state from DB, handles code proposals |
| Worker task | Done | Arq background task that runs agent service |

### MCP Tool Servers — 100% Complete

| Server | Status | What It Actually Does |
|--------|--------|----------------------|
| data_ingest | Done | Reads CSV/XLSX, profiles columns (dtypes, nulls, unique counts, min/max/mean), samples rows |
| merge_planner | Done | Detects join keys between tables by column name/type similarity, executes merges |
| dtype_manager | Done | Casts column types, suggests optimal types, validates type compatibility |
| preprocessing | Done | Handles missing values (median/mode/drop), encodes categoricals (label/onehot), scales numerics (standard/minmax) |
| eda_plots | Done | Generates matplotlib charts: histograms, correlation heatmaps, box plots, target analysis |
| hypothesis | Done | Generates hypotheses from column-target pairs, runs scipy.stats tests (t-test, chi-square, correlation, ANOVA) |
| modeling_explain | Done | Trains sklearn models (LogisticRegression, RandomForest, GradientBoosting, SVM), evaluates metrics, runs SHAP analysis |
| sandbox_executor | Done | AST-based code safety checking, import allowlist, subprocess execution with timeout |
| code_registry | Done | Stores/retrieves code snippets for the code approval workflow |
| session_doc | Done | Persists session context documents across pipeline steps |

### Testing — 272 Backend Tests + 91 Frontend Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| test_health.py | 2 | Health endpoint |
| test_sessions.py | 7 | Session CRUD |
| test_uploads.py | 4 | File upload |
| test_profiling.py | 18 | Column profiling, description updates, multi-sheet XLSX |
| test_events.py | 9 | SSE events, pagination, event types |
| test_artifacts.py | 9 | Artifact CRUD, download, metadata |
| test_code.py | 28 | Code proposal approve/deny, status transitions, context field |
| test_session_service.py | 15 | Step regression guard, service-layer CRUD |
| test_pipeline.py | 13 | Target identification, pipeline methods |
| test_custom_endpoints.py | 19 | select-model, train-additional, custom-plot, custom-hypothesis, retrain-threshold |
| test_self_heal.py | 18 | Two-phase approval, denial counts, reproposal logic, end-to-end cycles |
| test_feature_selection.py | 9 | Feature selection CRUD, step states, resume, rerun |
| test_data_ingest_sheets.py | 18 | Multi-sheet XLSX handling, sheet listing |
| test_modeling_explain.py | 33 | Model training, SHAP, leakage detection, temporal split, polynomial features |
| test_orchestrator.py | 25 | LLM orchestrator routing, fast-path guard, fallback, state summary |
| test_node_helpers.py | 8 | Trace event emission helpers |
| test_llm_json.py | 20 | LLM JSON parsing, retry logic, fence stripping |

**Frontend Tests (91):**

| Test File | Tests | Coverage |
|-----------|-------|----------|
| api-client.test.ts | 11 | API client fetch wrappers |
| use-wizard-navigation.test.ts | 8 | Wizard navigation, high water mark |
| stores.test.ts | 13 | Zustand stores (session, trace, modal) |
| use-event-stream.test.ts | 12 | SSE event stream hook |
| button.test.tsx | 3 | Button component variants |
| error-boundary.test.tsx | 3 | Error boundary rendering |
| use-rerun.test.ts | 6 | Rerun hook with step invalidation |
| trace-event-item.test.tsx | 26 | Trace event item rendering, expansion, event types |
| wizard-nav.test.tsx | 9 | Wizard navigation component |

---

## Is AI Included?

### The Honest Answer: Yes — Both ML and LLM

The project uses AI/ML at **three levels**: classical ML for modeling, SHAP for explainability, and Azure OpenAI GPT-4o for orchestration and analysis enhancement.

#### What IS Using AI/ML (Actually Running)

1. **Machine Learning Models** — The system **actually trains real scikit-learn models** on uploaded data:
   - Logistic Regression
   - Random Forest Classifier
   - Gradient Boosting Classifier
   - SVM (Support Vector Machine)
   - These produce real accuracy, precision, recall, F1, and AUC-ROC scores
   - Real confusion matrices are generated
   - Real 3-way splits (70/15/15 train/validation/test) with stratification
   - Hyperparameter tuning via RandomizedSearchCV
   - Overfit/underfit detection, class imbalance handling, target leakage detection
   - Time-aware (temporal) splitting for time-series data

2. **SHAP Explainability** — The system **actually runs SHAP** (SHapley Additive exPlanations) on trained models to explain which features drive predictions. This generates real feature importance rankings and waterfall plots.

3. **Statistical Hypothesis Testing** — The system **actually runs scipy.stats tests**:
   - Independent t-tests for numeric features vs binary targets
   - Chi-square tests for categorical features vs categorical targets
   - Pearson correlation for numeric-numeric relationships
   - ANOVA for numeric features vs multi-class targets
   - Real p-values and test statistics are computed

4. **LLM-Driven Orchestration** — Azure OpenAI GPT-4o is **connected and active** via `llm.py`:
   - **Pipeline orchestrator** — The LangGraph orchestrator node uses the LLM to decide which step to run next based on current state, session context, denial history, and artifact summary
   - **Recommendation generation** — LLM-enhanced VC-focused recommendations
   - **Report narratives** — LLM-enhanced executive summaries
   - **Self-correction** — `invoke_llm_json()` with retry logic handles parse failures by feeding errors back to the LLM

5. **LangGraph as an AI Orchestrator** — LangGraph uses a **hub-and-spoke architecture** where the orchestrator is the central decision hub:
   - LLM-driven conditional routing between 12 execution nodes
   - Fast-path guard for trivially deterministic cases (approval gates, all-done)
   - Fallback to first-READY-step heuristic when LLM call fails
   - Step state dependency DAG with invalidation support

#### Summary

| Component | Uses Real AI/ML? | How? |
|-----------|-----------------|------|
| Model training (sklearn) | **YES** | Trains 3-4 real ML models with hyperparameter tuning |
| SHAP analysis | **YES** | Computes real feature importance via SHAP library |
| Statistical testing (scipy) | **YES** | Runs real hypothesis tests with real p-values |
| Pipeline orchestration | **YES (LLM)** | GPT-4o decides next step via hub-and-spoke routing |
| Recommendations | **YES (LLM)** | LLM-enhanced VC-focused analysis |
| Report narrative | **YES (LLM)** | LLM-enhanced executive summaries |
| EDA chart generation | **No** (but real) | Uses matplotlib/pandas — standard data viz, not AI |
| Hypothesis generation | **No** | Keyword matching heuristics, NOT LLM-generated |
| Azure OpenAI (GPT-4o) | **Connected** | Used for orchestration, recommendations, reports |

---

## Detailed Capabilities — What It CAN Do

### 1. End-to-End Data Science Pipeline
Upload a CSV/XLSX file and the system will automatically:
- Profile every column (detect types, count nulls, compute statistics)
- Identify the best target variable for prediction (e.g., "Churn")
- Handle missing values (median imputation for numeric, mode for categorical)
- Encode categorical variables (label encoding)
- Scale numeric features (standard scaling)
- Generate 4+ types of EDA visualizations
- Run 3-6 statistical hypothesis tests
- Train 3 ML models and compare their performance
- Run SHAP analysis on the best model
- Generate an executive report with findings and recommendations

**How it does this:** The pipeline service (`pipeline_service.py`) or the LangGraph agent chain (`agent/nodes/`) executes each step sequentially. Each step uses real Python data science libraries (pandas, scikit-learn, scipy, matplotlib, SHAP).

### 2. Multi-File Data Merging
If you upload multiple CSV/XLSX files:
- The system detects potential join keys between tables (by matching column names and types)
- It generates and executes merge code to combine tables into a single analysis-ready dataset
- Supports inner, left, right, and outer joins

**How it does this:** The `merge_planner` MCP server compares column schemas across files, scores join key candidates by name similarity and type compatibility, and executes pandas merge operations.

### 3. Real-Time Progress Tracking
While the pipeline runs:
- Every step emits SSE (Server-Sent Events) to the frontend
- The Live Trace sidebar shows timestamped events: "Starting EDA...", "Training Random Forest...", "SHAP analysis complete"
- Events are persisted to the database, so you can review them later
- If you disconnect and reconnect, events resume from where you left off (via `Last-Event-ID`)

**How it does this:** `EventService` maintains per-session `asyncio.Queue` subscriber lists. When a pipeline step calls `_emit()`, the event is written to PostgreSQL AND pushed to all active SSE connections for that session. The frontend uses `EventSource` with auto-reconnect.

### 4. Human-in-the-Loop Code Approval
When the pipeline generates code (e.g., merge code, preprocessing code):
- A code proposal is created with status "pending"
- The frontend shows a Monaco editor modal with the generated code
- The user can approve, deny, or edit the code
- Only approved code gets executed

**How it does this:** Code proposals are stored in the `code_proposals` table. The frontend polls `GET /sessions/{id}/code/pending`. On approve, the backend marks the proposal as approved and proceeds. The sandbox executor runs approved code with AST-based safety checks and an import allowlist.

### 5. Session Persistence & History
- All sessions are saved to PostgreSQL with full state
- The landing page shows all past sessions with status, industry, company name, and date
- You can click any session to resume from where you left off
- The wizard remembers which steps you've completed (high water mark)

**How it does this:** The `sessions` table stores `current_step` (the furthest step reached). The frontend `useWizardNavigation` hook compares the URL step with the DB step to determine which steps are navigable. The backend's `session_service.py` has a regression guard that prevents `current_step` from ever going backwards.

### 6. Large File Handling
- Supports files up to 500MB
- Files larger than 100MB are read in 50,000-row chunks
- Profiling samples the first 100,000 rows for performance
- Model training uses the full dataset (or sampled for very large files)

**How it does this:** `pd.read_csv(chunksize=50000)` for chunked reading. The `data_ingest` MCP server's `_read_dataframe()` function checks file size and uses chunked reading when appropriate.

### 7. Sandbox Code Execution
- Generated code runs in a sandboxed environment
- AST parsing blocks dangerous patterns: `eval`, `exec`, `__import__`, `os.system`, `subprocess.run`, `shutil.rmtree`
- Only whitelisted imports are allowed (pandas, numpy, sklearn, matplotlib, plotly, scipy, etc.)
- Execution has a configurable timeout

**How it does this:** The `sandbox_executor` MCP server parses code into an AST, walks the tree to detect dangerous nodes (Import, Call, Attribute), checks against an allowlist, then executes via subprocess with a timeout.

### 8. Dark/Light Theme
- Toggle between dark and light mode with a button in the wizard nav
- Theme preference persists across page loads
- All UI components (charts, cards, tables) adapt to the theme

**How it does this:** `next-themes` library with `ThemeProvider` in root layout. `ThemeToggle` component calls `setTheme()`. Tailwind's `dark:` variant classes handle styling.

---

## Limitations — What It CANNOT Do

### 1. Limited Natural Language Interaction
- **Cannot understand natural language queries** about the data ("Why is churn high in Q3?")
- **Cannot write custom analysis code** based on a prompt ("Analyze seasonal patterns")
- The LLM drives orchestration decisions and enhances reports/recommendations, but does not power a conversational interface

### 2. Classification Only (No Regression)
- The system assumes a **classification task** (binary or multi-class)
- It cannot handle regression targets (predicting continuous values like revenue)
- Metrics shown are classification-specific: accuracy, precision, recall, F1, AUC-ROC, confusion matrix
- If no suitable binary/categorical target is found, the target identification may fail

**Why:** The modeling pipeline uses `LogisticRegression`, `RandomForestClassifier`, `GradientBoostingClassifier` — all classifiers. SHAP analysis is configured for tree-based classifiers.

### 3. No Deep Learning
- Only classical ML models (logistic regression, random forest, gradient boosting, SVM)
- No neural networks, transformers, or deep learning
- No GPU utilization
- Hyperparameter tuning uses RandomizedSearchCV (not exhaustive grid search)

**Why:** The scope was focused on interpretable models for VC use cases where explainability matters more than raw accuracy.

### 4. No Real-Time Data or Streaming Data
- Works on static file uploads only (CSV/XLSX)
- Cannot connect to databases, APIs, or streaming sources
- Time-series data is partially supported (temporal split detection) but no native temporal feature engineering

### 5. No Multi-User or Authentication
- No user accounts, login, or authentication
- No role-based access control
- Any user can see all sessions
- No API key protection (except rate limiting)

### 6. PPTX Export Not Implemented
- PDF and CSV report exports are fully implemented
- **PPTX export is not yet implemented** — the button exists but the endpoint is not available
- PDF uses ReportLab for professional formatting; CSV exports raw report data

### 7. Incremental Analysis is Partial
- Can re-run individual steps via `POST /sessions/{id}/rerun/{step}` with downstream invalidation
- Cannot add new data to an existing analysis
- Cannot compare multiple analyses side-by-side
- Must start a new session for a new dataset

### 8. In-Memory Limitations
- SSE event subscribers are in-memory — lost on server restart (clients auto-reconnect)
- Rate limiting counters are in-memory — reset on server restart
- No distributed state — single-server deployment only

### 9. No Automated Deployment
- No Kubernetes manifests, Terraform, or cloud deployment scripts
- Docker Compose exists but is for local development only
- No CI/CD deployment step (only lint + test)

---

## How It Works — Technical Deep Dive

### The Pipeline (Step by Step)

When a user clicks "Start Analysis" on the workspace page, here's exactly what happens:

#### Step 1: Opportunity Detection → Pipeline Trigger
```
Frontend: GET /sessions/{id}/opportunities
Backend:  PipelineService.get_opportunities()
          → Checks if artifacts exist for this session
          → If NO artifacts: calls run_pipeline(session_id)
          → If artifacts exist: returns cached opportunities (NO re-trigger)
```

#### Step 2: Data Loading
```
PipelineService._get_files(session_id)
→ Queries UploadedFile table for all files in this session
→ For each file, resolves storage_path relative to UPLOAD_DIR

PipelineService._load_dataframe(file)
→ Checks file_type (csv or xlsx)
→ pd.read_csv(path, nrows=100000) or pd.read_excel(path, nrows=100000)
→ Returns pandas DataFrame
```

#### Step 3: Target Identification
```
PipelineService._identify_target_column(df)
→ Checks column names against target_names list:
  ["churn", "target", "label", "class", "outcome", "churned",
   "is_churn", "attrition", "default", "fraud", "spam"]
→ If no match, looks for binary columns with values like
  {yes/no, true/false, 0/1, y/n}
→ Returns column name or None
```

#### Step 4: EDA Generation
```
PipelineService._run_eda(session_id, df, target_column)
→ Chart 1: Target Distribution
  - matplotlib bar chart of target value counts
  - Saved as PNG artifact to data/uploads/ with UUID filename

→ Chart 2: Correlation Heatmap
  - df.select_dtypes(include=[np.number]).corr()
  - Seaborn-style heatmap with annotations
  - Saved as PNG artifact

→ Chart 3: Missing Values
  - Horizontal bar chart of null percentages per column
  - Only shown if any column has nulls

→ Chart 4: Feature Distributions
  - Top 6 numeric columns plotted as histograms
  - 2x3 subplot grid

→ Each chart saved as Artifact record in DB with:
  - session_id, artifact_type="image", title, file_path
  - metadata_ JSON with plot type and description
```

#### Step 5: Hypothesis Testing
```
PipelineService._run_hypothesis_tests(session_id, df, target_column)
→ For each numeric column (vs binary target):
  - Splits data into two groups by target value
  - Runs scipy.stats.ttest_ind(group1, group2)
  - Creates Hypothesis record with:
    test_type="t_test", test_statistic, p_value,
    supported=(p_value < 0.05), conclusion text

→ For each categorical column (vs categorical target):
  - Builds contingency table with pd.crosstab()
  - Runs scipy.stats.chi2_contingency(contingency)
  - Creates Hypothesis record with:
    test_type="chi_square", test_statistic, p_value,
    supported=(p_value < 0.05), conclusion text
```

#### Step 6: Model Training
```
PipelineService._train_models(session_id, df, target_column)
→ Feature preparation:
  - Drops non-numeric columns (except target)
  - Label-encodes target if categorical
  - Fills NaN with column medians
  - StandardScaler on features

→ Train/test split: 80/20 with stratification

→ For each model in [LogisticRegression, RandomForest, GradientBoosting]:
  - model.fit(X_train, y_train)
  - y_pred = model.predict(X_test)
  - y_proba = model.predict_proba(X_test)[:, 1]
  - Computes: accuracy, precision, recall, f1, roc_auc
  - Computes: confusion_matrix
  - Marks is_best=True for highest F1 model

→ Generates feature importance bar chart for best model
→ Stores ModelResult records in DB/artifacts
```

#### Step 7: SHAP Analysis
```
PipelineService._run_shap(session_id, df, target_column, best_model)
→ Creates SHAP TreeExplainer (for tree models) or LinearExplainer
→ Computes shap_values on X_test sample (first 200 rows)
→ Generates:
  - Summary plot (beeswarm): shows feature impact distribution
  - Feature importance bar chart: mean absolute SHAP values
  - Waterfall plot: explains a single prediction
→ Saves plots as PNG artifacts
→ Returns top features with importance scores
```

#### Step 8: Report Generation
```
PipelineService._generate_report(session_id, results)
→ Compiles:
  - executive_summary: Template with company, target, best model, metrics
  - key_findings: List of significant results (model accuracy, hypothesis outcomes)
  - recommendations: VC-focused action items
  - model_summary: Best model name + metrics
  - hypothesis_summary: Count supported vs rejected
→ Saves as JSON artifact
→ Returns Report object to frontend
```

### The Frontend Data Flow

```
User visits /sessions/{sessionId}/models
  → React component mounts
  → useQuery fires: GET /sessions/{sessionId}/models
  → Backend returns ModelResult[] from DB
  → Frontend sorts by f1_score descending
  → Renders table with rank, model name, metrics
  → Click row → useState toggles open → shows confusion matrix
  → "Continue to SHAP" button:
    → useWizardNavigation("models").navigateToNext("shap")
    → If at frontier: PATCH /sessions/{id} {current_step: "shap"}, then navigate
    → If reviewing: just navigate (no DB mutation)
```

### The Wizard Navigation System

```
DB: session.current_step = "models"  (high water mark — furthest reached)
URL: /sessions/{id}/eda              (user navigated back to view EDA)

WizardNav renders:
  Steps 1-9 (onboarding through models): "completed" (clickable, green checkmark)
  Step 6 (eda): "current" (highlighted, blue)
  Steps 10-11 (shap, report): "locked" (grey, not clickable)

User clicks "Continue to Hypotheses" on EDA page:
  → useWizardNavigation("eda") detects: URL index (5) < DB index (8)
  → isAtFrontier = false → just router.push("/sessions/{id}/hypotheses")
  → No PATCH request → DB current_step stays at "models"

User navigates to models page, clicks "Continue to SHAP":
  → useWizardNavigation("models") detects: URL index (8) >= DB index (8)
  → isAtFrontier = true → PATCH /sessions/{id} {current_step: "shap"}
  → Backend session_service checks: "shap" (index 9) > "models" (index 8) → allows
  → DB current_step updated to "shap"
  → router.push("/sessions/{id}/shap")
```

---

## Implementation Status Table

| Layer | Component | Real Implementation? | Uses AI/ML? | Notes |
|-------|-----------|---------------------|-------------|-------|
| **Frontend** | Landing page + session history | Yes | No | React Query fetches from GET /sessions |
| **Frontend** | 11 wizard pages | Yes | No | All connected to real API endpoints |
| **Frontend** | Live trace sidebar | Yes | No | SSE streaming with auto-reconnect |
| **Frontend** | Code approval modal | Yes | No | Monaco editor, approve/deny workflow |
| **Frontend** | Theme toggle | Yes | No | next-themes dark/light mode |
| **Frontend** | Page transitions | Yes | No | Framer Motion AnimatePresence |
| **Frontend** | Error boundary | Yes | No | React class component with retry |
| **Backend** | Session CRUD | Yes | No | PostgreSQL + async SQLAlchemy |
| **Backend** | File upload | Yes | No | Multipart upload, validation, UUID storage |
| **Backend** | Column profiling | Yes | No | Pandas profiling with chunked reading |
| **Backend** | SSE event streaming | Yes | No | asyncio.Queue pub/sub |
| **Backend** | Rate limiting | Yes | No | In-memory, 100/min general, 10/min uploads |
| **Backend** | Path traversal protection | Yes | No | Validates resolved paths within upload_dir |
| **Backend** | Step regression guard | Yes | No | Prevents current_step from going backwards |
| **Backend** | Pipeline auto-trigger guard | Yes | No | Checks artifact count before re-running |
| **Backend** | File cleanup service | Yes | No | Deletes files >30 days for completed sessions |
| **Pipeline** | Data profiling | Yes | No | Pandas describe(), dtypes, null counts |
| **Pipeline** | Multi-file merge | Yes | No | Column name matching + pandas merge |
| **Pipeline** | Target identification | Yes | No | Keyword heuristics (not AI) |
| **Pipeline** | EDA chart generation | Yes | No | Matplotlib charts (not AI-generated) |
| **Pipeline** | Missing value handling | Yes | No | Median/mode imputation |
| **Pipeline** | Categorical encoding | Yes | No | Label encoding / one-hot encoding |
| **Pipeline** | Feature scaling | Yes | No | StandardScaler / MinMaxScaler |
| **Pipeline** | Hypothesis testing | Yes | **Yes (statistics)** | scipy.stats: t-test, chi-square, correlation, ANOVA |
| **Pipeline** | Model training | Yes | **Yes (ML)** | scikit-learn: LogReg, RF, GBM, SVM |
| **Pipeline** | Model evaluation | Yes | **Yes (ML)** | Accuracy, precision, recall, F1, AUC-ROC |
| **Pipeline** | SHAP analysis | Yes | **Yes (ML)** | SHAP TreeExplainer / LinearExplainer |
| **Pipeline** | Recommendations | Yes | No | Rule-based from model results (not AI) |
| **Pipeline** | Report generation | Yes | No | Template-based text (not LLM-written) |
| **Agent** | LangGraph hub-and-spoke | Yes | **Yes (LLM)** | LLM-driven orchestrator with fast-path guard and fallback |
| **Agent** | 12 agent nodes | Yes | Varies | Call MCP servers, some use ML, some use LLM |
| **Agent** | MCP bridge | Yes | No | Direct Python import, lazy loading |
| **Agent** | Agent service | Yes | No | Invokes compiled_graph.ainvoke(), manages code proposals |
| **Agent** | Worker task | Yes | No | Arq background job execution |
| **Agent** | Two-phase approval gate | Yes | No | Propose → approve/deny → self-heal (3 retries) |
| **LLM** | Azure OpenAI (GPT-4o) | **Connected** | **Yes** | Used for orchestration, recommendations, reports |
| **LLM** | LangChain + prompts | **Connected** | **Yes** | AzureChatOpenAI with retry logic, JSON parsing |
| **Export** | PDF report download | **Implemented** | No | ReportLab-based PDF generation |
| **Export** | CSV report download | **Implemented** | No | CSV export of report data |
| **Export** | PPTX report download | **NOT IMPLEMENTED** | N/A | Low priority — PDF/CSV cover main use cases |
| **Infra** | Authentication | **NOT IMPLEMENTED** | N/A | No user accounts or API keys |
| **Infra** | Production deployment | **NOT IMPLEMENTED** | N/A | Docker Compose is dev-only |
| **Testing** | Backend tests (272) | Yes | No | pytest + SQLite in-memory, comprehensive coverage |
| **Testing** | Frontend tests (91) | Yes | No | Vitest + React Testing Library, 9 test suites |
| **Testing** | E2E tests | Manual only | No | Verified via Playwright manually |
