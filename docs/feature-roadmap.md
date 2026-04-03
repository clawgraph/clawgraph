# ClawGraph — Feature Roadmap

> Last updated: 2026-04-03
> Status: Active development. v0.1.2 shipped to PyPI. Main now includes post-release security and TDD hardening, with 105 tests in the current suite.

---

## How to Use This Roadmap

Each feature is scoped as an **assignable unit of work** — one branch, one PR. Features include:
- **Priority** (P0 = must-have now, P1 = next, P2 = important, P3 = nice-to-have)
- **Effort** (S/M/L/XL)
- **Dependencies** (what must ship first)
- **Acceptance criteria** (how to verify it's done)
- **Suggested branch name**

Agents or contributors can pick up any feature by creating the branch and working through the acceptance criteria. Run `pytest` before pushing.

---

## Completed Work (v0.1.0 → current main)

The following shipped in v0.1.0–v0.1.2 and form the foundation for everything below:

- [x] **Core memory API** — `add()`, `query()`, `export()`, `add_batch()` (Python + CLI)
- [x] **Kùzu graph storage** — embedded, no server, MERGE-based idempotency
- [x] **LLM extraction** — NL → entities/relationships via OpenAI SDK (any compatible API)
- [x] **Ontology tracking** — auto-discovered schema, constraints, JSON persistence
- [x] **Snapshots** — save/load DB as `.tar.gz` for portability
- [x] **Timestamps** — `created_at`, `updated_at` on all entities and relationships
- [x] **Batch mode** — multiple facts in one LLM call
- [x] **JSON output** — `--output json` on all CLI commands
- [x] **Context manager** — `with Memory() as mem:` (PR #37)
- [x] **Security hardening** — injection prevention, path traversal protection, entity name validation, safe file permissions, info leak prevention (PR #36)
- [x] **CI pipeline** — pytest matrix (3.10–3.13, ubuntu+windows), ruff, mypy, daily pip-audit
- [x] **PyPI publishing** — Trusted Publishing (OIDC) + Sigstore attestations
- [x] **LobsterGym eval** — Docker Compose eval framework with browser tasks
- [x] **Write-path hardening** — explicit logical write groups plus transactional rollback on grouped write failure (PR #55)
- [x] **105 tests** — all mocked, no live API calls in CI
- [x] **Pre-commit hooks** — ruff + mypy (PR #24)
- [x] **CLI tests** — 13 tests covering all commands (PR #37)

### Open Draft PRs

| PR | Feature | Branch | Status |
|----|---------|--------|--------|
| #8 | Memory decay | `copilot/add-memory-decay-feature` | Draft — deprioritized |
| #10 | Confidence scoring | `copilot/add-confidence-scoring-relationships` | Draft |
| #11 | Tool-use definitions | `copilot/feattool-definitions` | Draft |
| #12 | Source provenance | `copilot/add-source-provenance-tracking` | Draft |
| #14 | Tiered LLM models | `copilot/add-tiered-models-support` | Draft |
| #15 | Workflow entity types | `copilot/add-workflow-step-tool-app-nodes` | Draft — deprioritized |

### Recently Merged on Main

- PR #36 — security hardening
- PR #37 — codebase quality and CLI tests
- PR #55 — TDD hardening for snapshot paths and grouped write execution

---

## Milestone: v0.2.0 — "Memory That Works"

**Goal:** Make ClawGraph production-ready for single-agent deployments. The graph must have clean data, be queryable reliably, and integrate with any agent framework with zero friction.
**Target:** 2026-04-15 (revised)

### F21: Entity Resolution & Deduplication ⭐ NEW
- **Priority:** P0
- **Effort:** M
- **Branch:** `feat/entity-resolution`
- **Dependencies:** None
- **Description:** Prevent semantic duplicates in the graph. "John Smith", "John", "john smith" should resolve to the same entity. Normalize names (case, whitespace, punctuation). Store aliases. On `add()`, check if an incoming entity is likely the same as an existing one (exact match after normalization → merge; close match → ask LLM to confirm). Without this, the graph fills with fragmented knowledge that never connects.
- **Files to create/modify:**
  - `src/clawgraph/db.py` — Add `aliases STRING` column to Entity, normalized name index
  - `src/clawgraph/memory.py` — Entity resolution logic in `_execute_inferred()`, alias management
  - `src/clawgraph/llm.py` — Optional LLM disambiguation ("Is 'JS' the same person as 'John Smith'?")
  - `tests/test_entity_resolution.py`
- **Acceptance criteria:**
  - [ ] `mem.add("John Smith works at Acme")` then `mem.add("john smith lives in NYC")` → single entity
  - [ ] Case/whitespace normalization happens automatically
  - [ ] `mem.add("JS joined Acme")` with existing "John Smith" → LLM asked to disambiguate
  - [ ] Entity aliases stored and searchable
  - [ ] `mem.entities()` returns canonical names with aliases
  - [ ] No regression on existing add/query behavior
  - [ ] Tests verify normalization, alias storage, disambiguation

---

### F22: Recall API — Context Injection for Agents ⭐ NEW
- **Priority:** P0
- **Effort:** M
- **Branch:** `feat/recall-api`
- **Dependencies:** None (enhanced by F01)
- **Description:** The API agents actually need. Instead of formulating precise queries, agents call `mem.recall(context="...", max_tokens=2000)` and get a pre-formatted block of relevant knowledge injected into their system prompt. This finds relevant entities via the LLM/graph, traverses 1–2 hops for related context, serializes as natural language, and trims to token budget. This is the difference between "a graph database wrapper" and "a memory system."
- **Files to create/modify:**
  - `src/clawgraph/memory.py` — Add `recall()` method
  - `src/clawgraph/llm.py` — Relevance scoring prompt, context serialization
  - `src/clawgraph/db.py` — Multi-hop traversal helper (`get_neighborhood(entity, hops=2)`)
  - `src/clawgraph/cli.py` — `clawgraph recall "context"` CLI command
  - `tests/test_recall.py`
- **Acceptance criteria:**
  - [ ] `mem.recall("user is asking about deployment")` returns relevant subgraph as formatted text
  - [ ] Result respects `max_tokens` budget (approximate, truncates least-relevant facts)
  - [ ] Traverses 1–2 hops from matched entities (e.g., find "deployment" → also returns team, tools, dates)
  - [ ] Returns empty string gracefully if nothing relevant found
  - [ ] Output format is agent-friendly (structured text, not raw JSON)
  - [ ] `clawgraph recall "context" --max-tokens 1000` CLI command works
  - [ ] Tests with mocked LLM and pre-populated graph

---

### F23: Relationship Properties ⭐ NEW
- **Priority:** P1
- **Effort:** M
- **Branch:** `feat/relationship-properties`
- **Dependencies:** None
- **Description:** The current `Relates` table only stores `type` and `created_at`. Real knowledge needs richer edges: "Alice was CEO of Acme from 2020 to 2024", "Bob knows Alice well (strength: 0.9)". Add a `properties JSON` column (or typed columns) for temporal qualifiers, strength, and arbitrary metadata. Update LLM extraction prompts to pull properties from statements.
- **Files to create/modify:**
  - `src/clawgraph/db.py` — Add `properties STRING` (JSON) column to Relates, migration
  - `src/clawgraph/llm.py` — Update extraction prompt to include relationship properties (dates, qualifiers)
  - `src/clawgraph/memory.py` — Pass properties through `_execute_inferred()`
  - `tests/test_relationship_properties.py`
- **Acceptance criteria:**
  - [ ] `mem.add("Alice was CEO of Acme from 2020 to 2024")` stores `{"from": "2020", "to": "2024"}` on relationship
  - [ ] `mem.relationships()` includes properties in output
  - [ ] Export includes relationship properties
  - [ ] Query results include relationship properties
  - [ ] Migration adds column to existing DBs without data loss
  - [ ] LLM prompt updated to extract temporal/qualifier info
  - [ ] Tests verify storage, retrieval, and migration

---

### F24: Delete / Retract / Correct ⭐ NEW
- **Priority:** P0
- **Effort:** S
- **Branch:** `feat/delete-retract`
- **Dependencies:** None
- **Description:** There's currently no way to remove or correct a fact. Agents make mistakes. People change jobs. If the graph only grows and never corrects, it becomes unreliable. Add `mem.retract(statement)` (LLM identifies what to remove), `mem.delete_entity(name)` (cascade delete entity + all relationships), and `mem.update(old, new)` (retract + add).
- **Files to create/modify:**
  - `src/clawgraph/memory.py` — Add `retract()`, `delete_entity()`, `update()` methods
  - `src/clawgraph/db.py` — Add `delete_entity(name)`, `delete_relationship(from, to, type)` methods
  - `src/clawgraph/llm.py` — Add retraction prompt (NL → identify entities/rels to remove)
  - `src/clawgraph/cli.py` — `clawgraph delete <entity>`, `clawgraph retract "statement"` commands
  - `tests/test_delete.py`
- **Acceptance criteria:**
  - [ ] `mem.delete_entity("Alice")` removes entity and all its relationships
  - [ ] `mem.retract("Alice works at Acme")` removes the specific relationship
  - [ ] `mem.update("Alice works at Acme", "Alice works at NewCo")` replaces the fact
  - [ ] `clawgraph delete Alice` CLI command works (with confirmation prompt)
  - [ ] `clawgraph retract "Alice works at Acme"` CLI command works
  - [ ] Cascade delete doesn't leave orphaned relationships
  - [ ] Ontology updated when last entity of a label type is removed
  - [ ] Tests verify delete, retract, update, and cascade behavior

---

### F01: Hybrid Retrieval (Graph + Vector Search)
- **Priority:** P0
- **Effort:** L
- **Branch:** `feat/hybrid-retrieval`
- **Dependencies:** None
- **Description:** Add optional vector embeddings alongside graph storage. When a Cypher query returns empty results, fall back to vector similarity search over entity names and descriptions. Use a lightweight embedding model (e.g., `sentence-transformers/all-MiniLM-L6-v2`) stored in a local FAISS/NumPy index.
- **Files to create/modify:**
  - `src/clawgraph/vectors.py` — Vector index wrapper (embed, store, search)
  - `src/clawgraph/memory.py` — Add `enable_vectors=True` param, fallback logic in `query()`
  - `src/clawgraph/db.py` — Store embedding alongside entity (or separate index file)
  - `tests/test_vectors.py` — Unit tests
  - `pyproject.toml` — Add `sentence-transformers` to optional deps `[vectors]`
- **Acceptance criteria:**
  - [ ] `Memory(enable_vectors=True)` initializes vector index
  - [ ] `mem.add("Alice works at Acme")` stores embedding for "Alice" and "Acme"
  - [ ] `mem.query("Who works at Acme?")` returns results from graph (primary)
  - [ ] `mem.query("Tell me about the company Acme Corp")` — name mismatch — falls back to vector search
  - [ ] Vector index persists to disk alongside Kùzu DB
  - [ ] `enable_vectors=False` (default) works exactly as before
  - [ ] Tests pass without network (mock embeddings)
  - [ ] Documented in README

---

### F02: Confidence Scoring
- **Priority:** P2
- **Effort:** M
- **Branch:** `feat/confidence-scoring`
- **Status:** PR #10 open (draft)
- **Dependencies:** None
- **Description:** Attach a confidence score (0.0–1.0) to each relationship. The LLM should estimate confidence during extraction. Low-confidence facts can be filtered or flagged.
- **Files to create/modify:**
  - `src/clawgraph/db.py` — Add `confidence FLOAT DEFAULT 1.0` to Relates schema
  - `src/clawgraph/llm.py` — Prompt LLM to include confidence in extraction output
  - `src/clawgraph/memory.py` — Add `min_confidence` filter to `query()`
  - `tests/test_confidence.py`
- **Acceptance criteria:**
  - [ ] New relationships have a `confidence` property (0.0–1.0)
  - [ ] `mem.query("...", min_confidence=0.8)` filters low-confidence results
  - [ ] Migration adds column to existing DBs without data loss
  - [ ] LLM prompt includes confidence estimation instructions
  - [ ] Tests with mocked LLM verify scoring

---

### F03: Source Provenance
- **Priority:** P1
- **Effort:** M
- **Branch:** `feat/source-provenance`
- **Status:** PR #12 open (draft)
- **Dependencies:** None
- **Description:** Track where each fact came from — which agent session, tool call, or user input. Store as properties on relationships: `source_agent`, `source_session`, `source_input`.
- **Files to create/modify:**
  - `src/clawgraph/db.py` — Add provenance columns to Relates
  - `src/clawgraph/memory.py` — Accept `source` metadata in `add()`/`add_batch()`
  - `tests/test_provenance.py`
- **Acceptance criteria:**
  - [ ] `mem.add("fact", source={"agent": "my-agent", "session": "abc123"})` stores provenance
  - [ ] `mem.query("...", source_agent="my-agent")` filters by source
  - [ ] Export includes provenance metadata
  - [ ] Migration for existing DBs
  - [ ] Tests verify storage and filtering

---

### F04: Memory Decay / Garbage Collection
- **Priority:** P3
- **Effort:** M
- **Branch:** `feat/memory-decay`
- **Status:** PR #8 open (draft)
- **Dependencies:** Timestamps (shipped), Entity resolution (F21)
- **Description:** Auto-demote or remove stale facts based on age and access frequency. Add an `access_count` property that increments on query hits. Provide `mem.prune(max_age_days=90, min_access_count=1)`.
- **Files to create/modify:**
  - `src/clawgraph/db.py` — Add `access_count INT DEFAULT 0`, `last_accessed STRING` to Entity
  - `src/clawgraph/memory.py` — Increment access count on query hits; add `prune()` method
  - `tests/test_decay.py`
- **Acceptance criteria:**
  - [ ] Entities track `access_count` and `last_accessed`
  - [ ] `mem.query()` increments access count for returned entities
  - [ ] `mem.prune(max_age_days=30)` removes entities untouched for 30+ days
  - [ ] `mem.prune(min_access_count=2)` removes rarely-accessed entities
  - [ ] Pruning is logged (which entities removed)
  - [ ] Tests with mocked timestamps

---

### F05: Tool-Use Function Definitions
- **Priority:** P1
- **Effort:** S
- **Branch:** `feat/tool-definitions`
- **Status:** PR #11 open (draft)
- **Dependencies:** None
- **Description:** Export ClawGraph operations as OpenAI/Anthropic function-calling tool definitions (JSON Schema). Any LLM-based agent can then call ClawGraph natively without the OpenClaw skill.
- **Files to create/modify:**
  - `src/clawgraph/tools.py` — Generate JSON Schema tool defs for add, query, export, add_batch
  - `src/clawgraph/cli.py` — `clawgraph tools export` command
  - `tests/test_tools.py`
- **Acceptance criteria:**
  - [ ] `clawgraph tools export` outputs valid JSON Schema for all operations
  - [ ] `clawgraph tools export --format openai` outputs OpenAI function-calling format
  - [ ] `clawgraph tools export --format anthropic` outputs Anthropic tool-use format
  - [ ] Schema validates against JSON Schema spec
  - [ ] Tests verify schema structure

---

## Milestone: v0.3.0 — "Workflow Memory"

**Goal:** Agents can record, recall, and learn from multi-step workflows.
**Target:** 2026-05-01 (revised — core memory quality comes first)

### F06: Workflow Entity Types
- **Priority:** P2
- **Effort:** M
- **Branch:** `feat/workflow-entities`
- **Status:** PR #15 open (draft) — deprioritized until core memory is solid
- **Dependencies:** None
- **Description:** Add `Workflow`, `Step`, `Tool`, `Application` node types to the base ontology. Define relationship types: `HAS_STEP`, `USED_TOOL`, `NEXT`, `ACCESSED_APP`.
- **Files to create/modify:**
  - `src/clawgraph/db.py` — Add new node/rel tables in `ensure_base_schema()`
  - `src/clawgraph/ontology.py` — Register workflow types in default ontology
  - `tests/test_workflow_schema.py`
- **Acceptance criteria:**
  - [ ] Schema includes Workflow, Step, Tool, Application tables
  - [ ] Relationship tables: HAS_STEP, USED_TOOL, NEXT, ACCESSED_APP
  - [ ] Migration adds tables to existing DBs
  - [ ] Ontology.summary() includes workflow types
  - [ ] Tests verify schema creation and migration

---

### F07: Workflow Logging API
- **Priority:** P2
- **Effort:** L
- **Branch:** `feat/workflow-logging`
- **Dependencies:** F06
- **Description:** `Memory.log_workflow(name, steps=[...])` — structured API to record a sequence of agent actions. Each step has: tool, input summary, output summary, duration, status.
- **Files to create/modify:**
  - `src/clawgraph/memory.py` — Add `log_workflow()`, `WorkflowStep` dataclass
  - `src/clawgraph/db.py` — MERGE logic for workflow/step nodes and relationships
  - `tests/test_workflow_logging.py`
- **Acceptance criteria:**
  - [ ] `mem.log_workflow("Deploy to staging", steps=[...])` creates graph substructure
  - [ ] Steps are connected with NEXT relationships (ordered)
  - [ ] Each step records: tool_name, input_summary, output_summary, duration_ms, status
  - [ ] Workflow has: name, started_at, finished_at, total_duration_ms, step_count
  - [ ] Duplicate workflows update rather than create (MERGE by name + timestamp)
  - [ ] Tests verify full graph structure

---

### F08: Workflow Retrieval
- **Priority:** P2
- **Effort:** M
- **Branch:** `feat/workflow-retrieval`
- **Dependencies:** F06, F07, F22 (recall API patterns)
- **Description:** `Memory.find_workflows(query)` — search for past workflows by natural language. Uses LLM to convert query to Cypher over workflow subgraph.
- **Files to create/modify:**
  - `src/clawgraph/memory.py` — Add `find_workflows()`, `get_workflow(id)`
  - `src/clawgraph/llm.py` — Workflow-specific Cypher generation prompt
  - `tests/test_workflow_retrieval.py`
- **Acceptance criteria:**
  - [ ] `mem.find_workflows("deploy")` returns matching workflows
  - [ ] `mem.get_workflow("workflow-id")` returns full step graph
  - [ ] Results include step details and ordering
  - [ ] Works with natural language queries
  - [ ] Tests with mocked LLM

---

### F09: Workflow Analytics
- **Priority:** P2
- **Effort:** S
- **Branch:** `feat/workflow-analytics`
- **Dependencies:** F06, F07
- **Description:** Built-in queries for workflow stats: most common workflows, average duration, failure rate by tool, most-used tools.
- **Files to create/modify:**
  - `src/clawgraph/memory.py` — Add `workflow_stats()` method
  - `src/clawgraph/cli.py` — `clawgraph workflows stats` command
  - `tests/test_workflow_analytics.py`
- **Acceptance criteria:**
  - [ ] `mem.workflow_stats()` returns dict with counts, durations, failure rates
  - [ ] `clawgraph workflows stats` CLI command with table output
  - [ ] `clawgraph workflows stats --output json` for machine-readable output
  - [ ] Tests verify stat calculations

---

## Milestone: v0.4.0 — "Scoped Memory"

**Goal:** One local agent can keep memory isolated across workflows, tasks, and threads; if shared deployments become important later, this milestone can extend into collaboration controls.
**Target:** TBD after v0.3.0 priorities settle

### F10: Workflow / Task / Thread Scoping
- **Priority:** P0
- **Effort:** L
- **Branch:** `feat/memory-scoping`
- **Dependencies:** None
- **Description:** Support `Memory(scope="deploy-incident-123")` or equivalent explicit workflow/task/thread scoping so one agent can keep separate jobs isolated without spinning up separate repos or databases. Scopes can map to the same Kuzu DB with metadata-based filtering or separate DB directories, but the user-facing goal is simple: memory for job A should not leak into job B unless asked.
- **Files to create/modify:**
  - `src/clawgraph/db.py` — Scope-aware storage model (metadata filter or separate directories)
  - `src/clawgraph/memory.py` — Accept `scope` param, scope all operations
  - `src/clawgraph/config.py` — Default scope config
  - `tests/test_scoping.py`
- **Acceptance criteria:**
  - [ ] `Memory(scope="task-a")` isolates from `Memory(scope="task-b")`
  - [ ] Default scope is `"default"` (backward compatible)
  - [ ] `mem.entities()` only returns entities from the active scope
  - [ ] `mem.query()` scopes to the active workflow/task/thread
  - [ ] Snapshots include scope metadata
  - [ ] Tests verify isolation and scoping

---

### F11: Access Control
- **Priority:** P1
- **Effort:** L
- **Branch:** `feat/access-control`
- **Dependencies:** F10, F03 (source provenance)
- **Description:** If shared deployments become a real use case, define who can read/write/admin each scope. Identity is established by an agent ID or API key passed at init time.
- **Files to create/modify:**
  - `src/clawgraph/auth.py` — Access control model (AgentIdentity, Permission, ACL)
  - `src/clawgraph/memory.py` — Enforce permissions on all operations
  - `src/clawgraph/config.py` — ACL config in YAML
  - `tests/test_access_control.py`
- **Acceptance criteria:**
  - [ ] `Memory(scope="shared-team-a", agent_id="agent-1")` establishes identity
  - [ ] Scope creator has admin permissions
  - [ ] Read/write/admin permissions are enforceable
  - [ ] Unauthorized operations raise `PermissionError`
  - [ ] ACL changes are audited
  - [ ] Tests verify all permission combinations

---

### F12: Audit Log
- **Priority:** P1
- **Effort:** M
- **Branch:** `feat/audit-log`
- **Dependencies:** F10, F11
- **Description:** Record who wrote/read/deleted what and when. Store as graph relationships for self-referential traceability: `(Agent)-[PERFORMED]->(Action{type, timestamp, target})`.
- **Files to create/modify:**
  - `src/clawgraph/db.py` — Audit node/rel tables
  - `src/clawgraph/memory.py` — Log operations automatically
  - `src/clawgraph/cli.py` — `clawgraph audit show` command
  - `tests/test_audit.py`
- **Acceptance criteria:**
  - [ ] All write operations create audit entries
  - [ ] `mem.audit_log(limit=50)` returns recent operations
  - [ ] `clawgraph audit show` CLI command
  - [ ] Audit entries include: agent_id, operation, target_entity, timestamp
  - [ ] Audit log cannot be tampered with (append-only)
  - [ ] Tests verify audit trail

---

### F13: Privacy Controls & Right-to-Forget
- **Priority:** P2
- **Effort:** M
- **Branch:** `feat/privacy-controls`
- **Dependencies:** F10, F11
- **Description:** If shared scopes emerge later, mark facts as `private` (agent-local), `scope`, or `public`. Implement `mem.forget(entity_name)` to purge an entity and all its relationships across all scopes. GDPR-style compliance.
- **Files to create/modify:**
  - `src/clawgraph/memory.py` — Add `visibility` param to `add()`, `forget()` method
  - `src/clawgraph/db.py` — Visibility column, cascade delete
  - `tests/test_privacy.py`
- **Acceptance criteria:**
  - [ ] `mem.add("fact", visibility="private")` restricts to current agent only
  - [ ] `mem.forget("Alice")` removes Alice and all relationships
  - [ ] Forget cascades across scopes if agent has admin
  - [ ] Forget is logged in audit trail
  - [ ] Tests verify visibility filtering and cascade delete

---

## Milestone: v0.5.0 — "Eval & CI"

**Goal:** LobsterGym is production-grade with regression tracking.
**Target:** 2026-04-15

### F14: LobsterGym Task Expansion (30+ Tasks)
- **Priority:** P1
- **Effort:** L
- **Branch:** `feat/lobstergym-tasks-v2`
- **Dependencies:** None
- **Description:** Expand from 12 to 30+ tasks. Add: multi-step browser workflows, API chains (read email → create calendar event → send reply), memory persistence tests (add facts → restart → recall), error recovery tasks, ambiguous instruction tasks.
- **Files to create/modify:**
  - `lobstergym/eval/tasks.py` — Add 18+ new tasks
  - `lobstergym/web/app.py` — New scenarios as needed
  - `lobstergym/api/app.py` — New endpoints as needed
  - `lobstergym/web/templates/` — New templates as needed
- **Acceptance criteria:**
  - [ ] 30+ tasks total across all categories
  - [ ] At least 5 memory-specific tasks
  - [ ] At least 5 multi-step tasks
  - [ ] All tasks have verification checks
  - [ ] Task difficulty distribution: ~10 easy, ~12 medium, ~8 hard
  - [ ] `python -m lobstergym.eval.runner --list` shows all tasks

---

### F15: Eval Regression Dashboard
- **Priority:** P2
- **Effort:** M
- **Branch:** `feat/eval-dashboard`
- **Dependencies:** F14
- **Description:** Generate an HTML dashboard from eval reports showing score trends over time. Store historical reports in `lobstergym/reports/` (committed as JSON, dashboard as generated HTML).
- **Files to create/modify:**
  - `lobstergym/eval/dashboard.py` — Generate HTML from report history
  - `lobstergym/eval/runner.py` — Append to history file
  - `.github/workflows/test.yml` — Deploy dashboard to GitHub Pages
- **Acceptance criteria:**
  - [ ] `python -m lobstergym.eval.dashboard` generates `dashboard.html`
  - [ ] Dashboard shows: score over time, task-level pass/fail matrix, profile comparison
  - [ ] Chart library: lightweight (Chart.js or inline SVG)
  - [ ] GitHub Actions uploads dashboard as artifact or deploys to Pages
  - [ ] Tests verify dashboard generation

---

### F16: LobsterGym Docker Image Publishing
- **Priority:** P2
- **Effort:** S
- **Branch:** `feat/lobstergym-ghcr`
- **Dependencies:** None
- **Description:** Publish lobstergym-web and lobstergym-api to GitHub Container Registry (GHCR) on release. This enables consuming them without building locally.
- **Files to create/modify:**
  - `.github/workflows/publish-containers.yml` — Build + push to GHCR on tag
  - `lobstergym/docker-compose.yml` — Update to reference GHCR images with fallback to local build
- **Acceptance criteria:**
  - [ ] `docker pull ghcr.io/clawgraph/lobstergym-web:latest` works
  - [ ] `docker pull ghcr.io/clawgraph/lobstergym-api:latest` works
  - [ ] Images are published on GitHub Release creation
  - [ ] Docker Compose works with both local build and GHCR images

---

## Milestone: v1.0.0 — "Production Ready"

**Goal:** Stable API, comprehensive docs, battle-tested eval scores.
**Target:** 2026-05-01

### F17: Schema Evolution & Migrations
- **Priority:** P1
- **Effort:** L
- **Branch:** `feat/schema-evolution`
- **Dependencies:** None
- **Description:** Handle ontology changes gracefully. When new properties are added to Entity or Relates, run ALTER TABLE. Track schema version in DB metadata. Provide `clawgraph db migrate` CLI command.
- **Files to create/modify:**
  - `src/clawgraph/migrations.py` — Migration registry and runner
  - `src/clawgraph/db.py` — Schema version tracking, migration hooks
  - `src/clawgraph/cli.py` — `clawgraph db migrate` command
  - `tests/test_migrations.py`
- **Acceptance criteria:**
  - [ ] Schema version tracked in DB metadata table
  - [ ] Migrations run automatically on `Memory()` init if needed
  - [ ] `clawgraph db migrate` runs pending migrations explicitly
  - [ ] Migrations are idempotent (safe to run multiple times)
  - [ ] Tests verify migration from v1 → v2 schema
  - [ ] Existing data is preserved through migrations

---

### F18: Comprehensive Documentation Site
- **Priority:** P1
- **Effort:** L
- **Branch:** `feat/docs-site`
- **Dependencies:** None
- **Description:** Build docs site at clawgraph.ai/docs using MkDocs Material. Auto-generate API reference from docstrings. Tutorials, architecture guide, contribution guide.
- **Files to create/modify:**
  - `docs/mkdocs.yml` — MkDocs config
  - `docs/docs/` — Markdown pages (quickstart, api, architecture, contributing)
  - `.github/workflows/docs.yml` — Deploy to GitHub Pages on push to main
- **Acceptance criteria:**
  - [ ] `mkdocs serve` runs locally
  - [ ] API reference auto-generated from docstrings
  - [ ] Pages: Home, Quickstart, Python API, CLI Reference, Architecture, Contributing
  - [ ] Deployed to clawgraph.ai/docs on merge to main
  - [ ] Search works
  - [ ] Mobile responsive

---

### F19: Plugin Architecture
- **Priority:** P2
- **Effort:** XL
- **Branch:** `feat/plugin-architecture`
- **Dependencies:** F01 (hybrid retrieval), F10 (scoping)
- **Description:** Define a `MemoryProvider` protocol that other frameworks can implement. ClawGraph becomes one implementation. Allow swapping backends (Kùzu, Neo4j, in-memory) and retrieval strategies (graph-only, vector-only, hybrid) via configuration.
- **Files to create/modify:**
  - `src/clawgraph/protocol.py` — `MemoryProvider` abstract protocol
  - `src/clawgraph/providers/kuzu.py` — Current impl, refactored to protocol
  - `src/clawgraph/providers/memory.py` — In-memory provider for testing
  - `tests/test_protocol.py`
- **Acceptance criteria:**
  - [ ] `MemoryProvider` protocol defines: add, query, export, entities, relationships
  - [ ] Kùzu provider passes all existing tests
  - [ ] In-memory provider works for testing/CI
  - [ ] Provider is configurable via config.yaml: `db.provider: kuzu`
  - [ ] Third parties can implement the protocol

---

### F20: Encryption at Rest
- **Priority:** P3
- **Effort:** L
- **Branch:** `feat/encryption-at-rest`
- **Dependencies:** F10 (scoping)
- **Description:** Encrypt sensitive facts in the DB. Use symmetric encryption (Fernet/AES-256). Key management via environment variable or config.
- **Files to create/modify:**
  - `src/clawgraph/crypto.py` — Encrypt/decrypt helpers
  - `src/clawgraph/db.py` — Transparent encryption on write, decrypt on read
  - `src/clawgraph/config.py` — Encryption key config
  - `tests/test_encryption.py`
- **Acceptance criteria:**
  - [ ] `Memory(encryption_key="...")` enables encryption
  - [ ] Entity names and relationship types are encrypted at rest
  - [ ] Queries still work (decrypt before LLM, encrypt result comparison)
  - [ ] Snapshots contain encrypted data
  - [ ] Missing key raises clear error
  - [ ] Tests verify encrypt/decrypt roundtrip

---

## Quick Wins (any time, low effort)

| ID | Task | Effort | Branch | Status |
|----|------|--------|--------|--------|
| QW01 | Add CI badge to README | S | `chore/ci-badge` | |
| QW02 | CONTRIBUTING.md | S | `docs/contributing` | |
| QW03 | Enable GitHub Discussions | S | (repo settings) | |
| QW04 | README demo GIF (asciinema/VHS) | S | `docs/demo-gif` | |
| QW05 | `clawgraph version` CLI command | S | `feat/version-command` | ✅ shipped (--version flag) |
| QW06 | `clawgraph stats` — entity/relationship counts | S | `feat/stats-command` | |
| QW07 | `clawgraph delete` — remove entity by name | S | `feat/delete-command` | → see F24 |
| QW08 | `clawgraph clear` — wipe all data (with confirmation) | S | `feat/clear-command` | |
| QW09 | Better error messages for missing API keys | S | `fix/api-key-errors` | |
| QW10 | Pre-commit hook config (ruff + mypy) | S | `chore/pre-commit` | ✅ shipped (PR #24) |

---

## Priority Matrix

```
            ┌───────────────────────────────────────────────────┐
            │           IMPACT                                   │
            │   High                             Low             │
        ────┼───────────────────────────────────────────────────┤
  HIGH  U   │ F21 Entity Resolution       F05 Tool Defs         │
  R     R   │ F22 Recall API              F09 Wf Analytics      │
  G     G   │ F01 Hybrid Retrieval        QW01-QW10             │
  E     E   │ F24 Delete/Retract                                │
  N     N   │ F03 Source Provenance                              │
  C     C   │                                                    │
  Y     Y   ├────────────────────────────────────────────────────┤
        ────│ F23 Relationship Properties  F15 Eval Dashboard   │
  LOW       │ F02 Confidence Scoring       F16 GHCR Images      │
            │ F06 Workflow Entities         F20 Encryption       │
            │ F07 Workflow Logging          F04 Memory Decay     │
            │ F10 Workflow / Task / Thread Scoping               │
            │ F17 Schema Evolution                               │
            │ F18 Docs Site                                      │
            │ F19 Plugin Architecture                            │
            └────────────────────────────────────────────────────┘
```

## Suggested Agent Assignment Order

For overnight / async agent work, assign in this order:

1. **F21: Entity Resolution** — data quality foundation, everything downstream depends on it
2. **F24: Delete / Retract / Correct** — small, essential for memory accuracy
3. **F22: Recall API** — the actual API agents need for context injection
4. **F05: Tool Definitions** (PR #11) — small, self-contained, unlocks zero-friction integration
5. **F03: Source Provenance** (PR #12) — medium, trust layer for facts
6. **F01: Hybrid Retrieval** — large, high-impact, core differentiator
7. **F23: Relationship Properties** — medium, enriches graph expressiveness
8. **F02: Confidence Scoring** (PR #10) — medium, quality signal on facts
9. **Quick Wins batch** (QW01–QW10) — low risk, polish, builds adoption
10. **F06 + F07: Workflow Entities + Logging** — large, sequential dependency
11. **F10: Workflow / Task / Thread Scoping** — large, unlocks scoped-memory and later shared-memory features
12. **F14: LobsterGym Task Expansion** — can run in parallel with above

Features F11–F13, F17–F20 should wait until earlier features are merged and stable.

---

## Branch Naming Convention

```
feat/   — New features (feat/hybrid-retrieval)
fix/    — Bug fixes (fix/api-key-errors)
docs/   — Documentation (docs/contributing)
chore/  — Maintenance (chore/ci-badge)
test/   — Test additions (test/workflow-schema)
```

## Definition of Done (all features)

- [ ] Code in `src/clawgraph/` with type hints
- [ ] Tests in `tests/` — all passing
- [ ] `ruff check` passes
- [ ] `mypy` passes (or `--ignore-missing-imports` for new deps)
- [ ] Docstrings on all public functions (Google style)
- [ ] README updated if user-facing
- [ ] PR description with summary and test instructions
