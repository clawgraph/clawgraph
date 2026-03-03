# ClawGraph — Solution Exploration

> Last updated: 2026-03-03

## What Is ClawGraph?

ClawGraph is a **graph-based memory layer for AI agents**. It takes natural-language statements, uses an LLM to extract entities and relationships, and stores them in an embedded Kùzu graph database using Cypher. Agents can then query their memory with natural language and get structured results back.

**Today it works.** You can `pip install clawgraph`, store facts, query them, snapshot the DB, and plug it into OpenClaw as a skill. The question is: what does the full picture look like?

---

## The Problem Space

AI agents today have a memory problem:

1. **Session amnesia** — Most agents forget everything between conversations. Context windows are large but not permanent.
2. **Flat memory** — Tools like vector stores (ChromaDB, Pinecone) treat memory as bags of text chunks. This works for similarity search but loses structure: "Alice works at Acme" and "Bob manages Alice" are separate embeddings with no queryable relationship.
3. **No shared context** — Multi-agent setups can't share knowledge without brittle glue code.
4. **No workflow memory** — Agents repeat the same multi-step tasks without learning from prior executions.
5. **Evaluation is guesswork** — There's no standard way to measure whether memory actually helps agent performance.

## Where ClawGraph Fits

ClawGraph solves **structured, persistent, queryable memory** using a knowledge graph:

```
                 ┌─────────────────────────────────────────────────┐
                 │                  Agent Runtime                   │
                 │  (OpenClaw, LangChain, AutoGPT, custom, etc.)  │
                 └──────────────┬──────────────────────────────────┘
                                │
                   ┌────────────▼────────────────┐
                   │        ClawGraph API         │
                   │  add() / query() / export()  │
                   │  add_batch() / snapshots()   │
                   └────┬──────────────┬──────────┘
                        │              │
              ┌─────────▼──────┐  ┌────▼─────────┐
              │  LLM (LiteLLM) │  │  Kùzu Graph  │
              │  Entity/Rel    │  │  (embedded)   │
              │  extraction    │  │  Cypher store  │
              └────────────────┘  └───────────────┘
```

### What makes this different from vector memory?

| Aspect | Vector Store | ClawGraph (Graph) |
|--------|-------------|-------------------|
| Storage model | Chunks of text → embeddings | Entities → Relationships → Properties |
| Query style | "Find similar text" | "Who manages Alice?" / "What tools did I use yesterday?" |
| Structure | Flat (similarity only) | Structured (traversable graph) |
| Deduplication | Hard (similarity threshold) | Built-in (MERGE by primary key) |
| Multi-hop reasoning | Impossible natively | Natural (graph traversal) |
| Temporal queries | Metadata filter | First-class timestamps + decay |

### Where vector stores still win

- **Semantic similarity search** on unstructured text (documents, long passages)
- **Speed at scale** for nearest-neighbor retrieval
- **No LLM call needed** at write time (embed and store)

### The hybrid opportunity

ClawGraph + vector search is the ideal combo. Graph for structure, vectors for fuzzy recall. This is a key roadmap item (see Feature Roadmap).

---

## Competitive Landscape

### Direct competitors (graph memory for agents)

| Tool | Approach | Pros | Cons |
|------|----------|------|------|
| **Mem0** | Hybrid vector+graph memory | Popular, well-funded | Hosted service, vendor lock-in, opaque graph |
| **Zep** | Temporal knowledge graph + vector | Session-aware, commercial support | Closed-source core, server-dependent |
| **Letta (MemGPT)** | LLM-managed memory tiers | Research-backed, novel architecture | Complex, slow (multiple LLM calls per operation) |
| **Graphiti** (by Zep) | Temporal KG for agents | Open-source, bi-temporal | Early stage, Zep ecosystem lock-in |

### Indirect competitors (vector-only memory)

ChromaDB, Pinecone, Weaviate, Qdrant, LanceDB — all good at similarity search, none provide structured graph queries.

### ClawGraph's differentiation

1. **Fully embedded** — no server, no cloud dependency. Kùzu runs in-process like SQLite.
2. **Open-source, permissive license** (Apache-2.0)
3. **LLM-agnostic** — LiteLLM supports any provider
4. **Agent-framework agnostic** — Python API works anywhere; OpenClaw skill is just one integration
5. **Portable** — snapshot to `.tar.gz`, restore anywhere
6. **Idempotent** — MERGE-based writes; safe to re-add facts
7. **Inspectable** — Cypher queries, JSON export, ontology tracking

### Where ClawGraph is weaker today

- No vector search (planned)
- No multi-agent sync (planned)
- No hosted offering (by design, for now)
- Small community (brand new)
- Single-node only (Kùzu limitation, but fine for agent workloads)

---

## Architecture Deep Dive

### Current stack

```
src/clawgraph/
├── cli.py          Typer CLI (add, query, export, ontology, config)
├── memory.py       High-level Python API (Memory class)
├── db.py           Kùzu wrapper (schema, CRUD, snapshots)
├── llm.py          LiteLLM integration (entity extraction, Cypher gen)
├── cypher.py       Cypher validation and sanitization
├── ontology.py     Schema tracking (labels, relationship types)
├── config.py       YAML config loader (~/.clawgraph/config.yaml)
```

### Current schema

```cypher
CREATE NODE TABLE Entity (
    name STRING PRIMARY KEY,
    label STRING,
    created_at STRING,
    updated_at STRING
)

CREATE REL TABLE Relates (
    FROM Entity TO Entity,
    type STRING,
    created_at STRING
)
```

### Data flow: `mem.add("Alice works at Acme")`

1. LLM extracts: `Entity(Alice, Person)`, `Entity(Acme, Organization)`, `Rel(Alice, WORKS_AT, Acme)`
2. LLM generates MERGE Cypher with timestamps
3. Cypher is validated (no CREATE, no injection, balanced parens)
4. Cypher executes against Kùzu
5. Ontology auto-updates with new labels/types

### Data flow: `mem.query("Who works at Acme?")`

1. LLM converts question → Cypher (MATCH query)
2. Cypher is validated (read-only, no mutation)
3. Cypher executes against Kùzu
4. Results returned as list of dicts

---

## LobsterGym — The Evaluation Story

LobsterGym exists to answer: **"Does graph memory actually help agents perform tasks better?"**

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Compose                           │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │ lobstergym-  │  │ lobstergym-  │    Mock services         │
│  │ web (:8080)  │  │ api (:8090)  │    (Flask + FastAPI)     │
│  └──────┬───────┘  └──────┬───────┘                         │
│         │                 │                                   │
│  ┌──────▼─────────────────▼───────┐                         │
│  │     OpenClaw + ClawGraph       │    Agent WITH memory     │
│  │         (:18789)               │                          │
│  └──────────────┬─────────────────┘                         │
│                 │                                             │
│  ┌──────────────▼─────────────────┐                         │
│  │     OpenClaw (default)         │    Agent WITHOUT memory  │
│  │         (:18790)               │                          │
│  └──────────────┬─────────────────┘                         │
│                 │                                             │
│  ┌──────────────▼─────────────────┐                         │
│  │       Eval Runner              │    Score + compare       │
│  │   (12 tasks, 4 categories)     │                          │
│  └────────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

### What we measure

- **Task completion rate** (pass/fail per task)
- **Score by category** (browser, API, memory, multi-step)
- **Score by difficulty** (easy, medium, hard)
- **ClawGraph vs. default** (side-by-side comparison)
- **Duration per task** (agent speed)

### Current task inventory: 12 tasks

| Category | Easy | Medium | Hard |
|----------|------|--------|------|
| Browser  | 1    | 3      | 1    |
| API      | 2    | 2      | 1    |
| Memory   | 1    | 0      | 0    |
| Multi    | 0    | 0      | 1    |

### Key insight

Memory tasks and multi-step tasks are where ClawGraph should show the biggest delta. Browser/API tasks test baseline agent competence. The eval framework lets us prove (or disprove) that graph memory adds real value.

---

## Target Users

### Primary: Agent developers

- Building with OpenClaw, LangChain, CrewAI, AutoGPT, custom frameworks
- Need persistent memory that survives sessions
- Want structured queries, not just similarity search
- Value embedded (no server) over hosted

### Secondary: AI/ML researchers

- Studying agent memory architectures
- Need reproducible benchmarks (LobsterGym)
- Comparing graph vs. vector vs. hybrid approaches

### Tertiary: Enterprise AI teams

- Multi-agent deployments with shared knowledge requirements
- Compliance needs (audit trail, right-to-forget)
- On-prem preference (no cloud dependency)

---

## Open Technical Questions

### 1. Hybrid retrieval (graph + vector)

How should we combine graph queries with vector similarity? Options:
- **A)** Embed entity descriptions, store embeddings alongside graph → query both, merge results
- **B)** Use vector search as a fallback when Cypher returns empty
- **C)** Let the LLM decide which retrieval method to use per query

**Recommendation:** Start with (B) — it's the simplest and covers the most common failure mode (entity name not matching exactly). Graduate to (A) when we have enough usage data.

### 2. Multi-agent memory sharing

What's the right abstraction for shared memory?
- **Namespaced graphs** (simplest — `Memory(namespace="team-X")`)
- **Graph federation** (each agent has local graph + sync protocol to share)
- **Central graph server** (defeats the embedded advantage)

**Recommendation:** Namespaced graphs first. Federation is a v2.0 problem.

### 3. Workflow capture granularity

How much of an agent's execution should we capture?
- Every tool call and result?
- Just the high-level steps?
- User-controlled granularity?

**Recommendation:** User-controlled with sensible defaults. Capture step-level (tool + input + output summary), not raw payloads. Let users opt into full capture.

### 4. LLM cost at write time

Every `add()` costs an LLM call to extract entities. At scale, this adds up.
- **Option A:** Cache extraction results for identical inputs
- **Option B:** Local NER model for simple facts, LLM only for complex ones
- **Option C:** Batch aggressively (`add_batch()` already does this)

**Recommendation:** (A) + (C) immediately. (B) as an optional "offline mode" later.

### 5. Schema evolution

What happens when the ontology changes? Today: new labels/types are auto-added, but there's no migration for property changes.
- Need `ALTER TABLE` support or graph rebuild
- Kùzu supports `ALTER TABLE ADD COLUMN` — leverage this

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM extraction inaccuracy | Medium | High | Validation layer, confidence scoring, human review mode |
| Kùzu breaking changes | Low | Medium | Pin version, test matrix, snapshot format versioning |
| OpenClaw API/skill spec changes | Medium | Medium | Abstraction layer, version checks |
| Competition from Mem0/Zep | High | Medium | Focus on embedded/open-source niche, hybrid retrieval |
| Slow adoption | Medium | High | LobsterGym benchmarks, blog posts, conference talks |
| LLM costs at scale | Medium | Medium | Caching, batching, local NER fallback |

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-01 | Kùzu over Neo4j | Embedded, no server, native Cypher, Apache-2.0 |
| 2026-03-01 | LiteLLM over direct SDKs | Provider-agnostic, one API for all LLMs |
| 2026-03-01 | Typer over Click | Type-hint driven, less boilerplate |
| 2026-03-01 | YAML config over TOML | Human-readable, simple config needs |
| 2026-03-02 | Apache-2.0 license | Enterprise-friendly, permissive |
| 2026-03-03 | LobsterGym in-repo (not separate) | Tight coupling with ClawGraph, one consumer |
| 2026-03-03 | Docker-in-Docker for Codespaces | Enables LobsterGym runs inside cloud dev env |
| 2026-03-03 | Nightly eval schedule | Catch regressions without manual trigger overhead |
