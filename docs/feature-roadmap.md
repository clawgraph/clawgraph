# ClawGraph — Feature Roadmap

> Last updated: 2026-03-03
> Status: Active development. v0.1.0 shipped. Persistence + LobsterGym in PR #2.

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

## Milestone: v0.2.0 — "Memory That Works"

**Goal:** Make ClawGraph production-ready for single-agent deployments.
**Target:** 2026-03-10

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
- **Priority:** P1
- **Effort:** M
- **Branch:** `feat/confidence-scoring`
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
- **Priority:** P2
- **Effort:** M
- **Branch:** `feat/memory-decay`
- **Dependencies:** Timestamps (already shipped in persistence PR)
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
**Target:** 2026-03-20

### F06: Workflow Entity Types
- **Priority:** P0
- **Effort:** M
- **Branch:** `feat/workflow-entities`
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
- **Priority:** P0
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
- **Priority:** P1
- **Effort:** M
- **Branch:** `feat/workflow-retrieval`
- **Dependencies:** F06, F07
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

## Milestone: v0.4.0 — "Multi-Agent Memory"

**Goal:** Multiple agents can share memory with access controls.
**Target:** 2026-04-05

### F10: Namespaced Memory
- **Priority:** P0
- **Effort:** L
- **Branch:** `feat/namespaced-memory`
- **Dependencies:** None
- **Description:** Support `Memory(namespace="team-X")` — each namespace gets its own isolated graph in the same Kùzu DB (or separate DB directory). Agents in the same namespace share knowledge.
- **Files to create/modify:**
  - `src/clawgraph/db.py` — Namespace-aware schema (prefix tables or separate directories)
  - `src/clawgraph/memory.py` — Accept `namespace` param, scope all operations
  - `src/clawgraph/config.py` — Default namespace config
  - `tests/test_namespaces.py`
- **Acceptance criteria:**
  - [ ] `Memory(namespace="team-a")` isolates from `Memory(namespace="team-b")`
  - [ ] Default namespace is `"default"` (backward compatible)
  - [ ] `mem.entities()` only returns entities from the active namespace
  - [ ] `mem.query()` scopes to namespace
  - [ ] Snapshots include namespace metadata
  - [ ] Tests verify isolation and scoping

---

### F11: Access Control
- **Priority:** P1
- **Effort:** L
- **Branch:** `feat/access-control`
- **Dependencies:** F10, F03 (source provenance)
- **Description:** Define who can read/write/admin each namespace. Identity is established by an agent ID or API key passed at init time.
- **Files to create/modify:**
  - `src/clawgraph/auth.py` — Access control model (AgentIdentity, Permission, ACL)
  - `src/clawgraph/memory.py` — Enforce permissions on all operations
  - `src/clawgraph/config.py` — ACL config in YAML
  - `tests/test_access_control.py`
- **Acceptance criteria:**
  - [ ] `Memory(namespace="team-a", agent_id="agent-1")` establishes identity
  - [ ] Namespace creator has admin permissions
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
- **Description:** Mark facts as `private` (agent-local), `team` (namespace), or `public`. Implement `mem.forget(entity_name)` to purge an entity and all its relationships across all namespaces. GDPR-style compliance.
- **Files to create/modify:**
  - `src/clawgraph/memory.py` — Add `visibility` param to `add()`, `forget()` method
  - `src/clawgraph/db.py` — Visibility column, cascade delete
  - `tests/test_privacy.py`
- **Acceptance criteria:**
  - [ ] `mem.add("fact", visibility="private")` restricts to current agent only
  - [ ] `mem.forget("Alice")` removes Alice and all relationships
  - [ ] Forget cascades across namespaces if agent has admin
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
- **Dependencies:** F01 (hybrid retrieval), F10 (namespaces)
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
- **Dependencies:** F10 (namespaces)
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

| ID | Task | Effort | Branch |
|----|------|--------|--------|
| QW01 | Add CI badge to README | S | `chore/ci-badge` |
| QW02 | CONTRIBUTING.md | S | `docs/contributing` |
| QW03 | Enable GitHub Discussions | S | (repo settings, no branch needed) |
| QW04 | README demo GIF (asciinema/VHS) | S | `docs/demo-gif` |
| QW05 | `clawgraph version` CLI command | S | `feat/version-command` |
| QW06 | `clawgraph stats` — entity/relationship counts | S | `feat/stats-command` |
| QW07 | `clawgraph delete` — remove entity by name | S | `feat/delete-command` |
| QW08 | `clawgraph clear` — wipe all data (with confirmation) | S | `feat/clear-command` |
| QW09 | Better error messages for missing API keys | S | `fix/api-key-errors` |
| QW10 | Pre-commit hook config (ruff + mypy) | S | `chore/pre-commit` |

---

## Priority Matrix

```
            ┌───────────────────────────────────────────────┐
            │           IMPACT                               │
            │   High                           Low           │
        ────┼───────────────────────────────────────────────┤
  HIGH  U   │ F01 Hybrid Retrieval      F05 Tool Defs       │
  R     R   │ F06 Workflow Entities      F09 Wf Analytics    │
  G     G   │ F07 Workflow Logging       QW01-QW10           │
  E     E   │ F10 Namespaced Memory                          │
  N     N   │ F14 Task Expansion                             │
  C     C   │                                                │
  Y     Y   ├────────────────────────────────────────────────┤
        ────│ F02 Confidence Scoring     F15 Eval Dashboard  │
  LOW       │ F03 Source Provenance      F16 GHCR Images     │
            │ F08 Wf Retrieval           F20 Encryption      │
            │ F11 Access Control                             │
            │ F12 Audit Log                                  │
            │ F13 Privacy Controls                           │
            │ F17 Schema Evolution                           │
            │ F18 Docs Site                                  │
            │ F19 Plugin Architecture                        │
            └────────────────────────────────────────────────┘
```

## Suggested Agent Assignment Order

For overnight / async agent work, assign in this order:

1. **Quick Wins batch** (QW01–QW10) — low risk, high volume, builds momentum
2. **F05: Tool Definitions** — small, self-contained, immediately useful
3. **F02: Confidence Scoring** — medium, teaches agents the codebase patterns
4. **F03: Source Provenance** — medium, similar pattern to F02
5. **F01: Hybrid Retrieval** — large, high-impact, core differentiator
6. **F06 + F07: Workflow Entities + Logging** — large, sequential dependency
7. **F14: LobsterGym Task Expansion** — can run in parallel with F06/F07
8. **F10: Namespaced Memory** — large, unlocks multi-agent features

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
