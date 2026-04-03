# ClawGraph - Architecture Snapshot

> Last updated: 2026-04-03
> Scope: current repository shape plus the runtime architecture of the published Python package

This note is a current-state map of the repo as it exists today. It is not a roadmap. It is a description of what is actually wired up now.

---

## 1. Repository Map

```mermaid
graph TD
    ROOT["clawgraph repo"]

    ROOT --> SRC["src/clawgraph<br/>published Python package"]
    ROOT --> TESTS["tests<br/>105 collected pytest tests"]
    ROOT --> SKILL["skills/clawgraph/SKILL.md<br/>OpenClaw skill instructions"]
    ROOT --> GYM["lobstergym<br/>evaluation harness + mock services"]
    ROOT --> DOCS["docs<br/>architecture, roadmap, exploration notes"]
    ROOT --> SITE["README.md + site/index.html<br/>project framing + landing page"]
    ROOT --> BUILD["pyproject.toml + GitHub Actions<br/>package, lint, typing, CI"]

    SRC --> CLI["cli.py<br/>Typer CLI"]
    SRC --> MEM["memory.py<br/>high-level memory API"]
    SRC --> LLM["llm.py<br/>OpenAI SDK integration"]
    SRC --> DB["db.py<br/>Kuzu wrapper + snapshots"]
    SRC --> ONT["ontology.py<br/>schema tracking"]
    SRC --> CYPHER["cypher.py<br/>validation + sanitization"]
    SRC --> CFG["config.py<br/>YAML config loader"]
    SRC --> MAIN["__main__.py / __init__.py"]

    GYM --> WEB["web<br/>Flask mock websites"]
    GYM --> API["api<br/>FastAPI mock APIs"]
    GYM --> EVAL["eval<br/>runner + tasks"]
    GYM --> REPORTS["reports<br/>evaluation output"]
    GYM --> COMPOSE["docker-compose.yml<br/>side-by-side profiles"]

    style ROOT fill:#16213e,stroke:#e94560,color:#fff
    style SRC fill:#0f3460,stroke:#e94560,color:#fff
    style GYM fill:#0f3460,stroke:#e94560,color:#fff
    style TESTS fill:#533483,stroke:#fff,color:#fff
    style DOCS fill:#533483,stroke:#fff,color:#fff
    style SKILL fill:#533483,stroke:#fff,color:#fff
    style SITE fill:#533483,stroke:#fff,color:#fff
    style BUILD fill:#533483,stroke:#fff,color:#fff
```

---

## 2. Product Framing

ClawGraph is currently best understood as a local-first graph memory layer for agents.

The repo is doing four jobs at once:

1. A Python package for persistent graph memory
2. A CLI for storing and querying memory without writing code
3. An OpenClaw skill / integration surface
4. A LobsterGym-based evaluation setup for measuring memory effects

The architectural bias is deliberate:

1. Embedded storage over a hosted service
2. Inspectable graph state over opaque memory blobs
3. Small Python-first API over a broad platform surface
4. OpenAI-compatible LLM support today, broader provider support later
5. Kuzu today, additional database backends later

---

## 3. Core Runtime Architecture

```mermaid
graph LR
    U1["CLI user"] --> CLI["cli.py"]
    U2["Python agent/app"] --> MEM["Memory API"]
    U3["OpenClaw skill"] --> MEM

    CLI --> MEM
    MEM --> ONT["Ontology"]
    MEM --> LLM["LLM layer"]
    MEM --> CYPHER["Cypher validation"]
    MEM --> DB["GraphDB"]
    LLM --> CFG["Config loader"]
    LLM --> OPENAI["OpenAI SDK"]
    OPENAI --> PROVIDER["OpenAI-compatible endpoint"]
    DB --> KUZU["Kuzu embedded DB"]
    ONT --> ONTFILE["ontology.json"]
    CFG --> CFGFILE["config.yaml"]
    DB --> DBFILES["~/.clawgraph/data"]
    DB --> SNAP[".tar.gz snapshots"]

    style CLI fill:#e94560,stroke:#fff,color:#fff
    style MEM fill:#16213e,stroke:#e94560,color:#fff
    style ONT fill:#533483,stroke:#fff,color:#fff
    style LLM fill:#533483,stroke:#fff,color:#fff
    style CYPHER fill:#533483,stroke:#fff,color:#fff
    style DB fill:#533483,stroke:#fff,color:#fff
    style OPENAI fill:#0f3460,stroke:#e94560,color:#fff
    style PROVIDER fill:#0f3460,stroke:#e94560,color:#fff
    style KUZU fill:#0f3460,stroke:#e94560,color:#fff
```

### Current boundaries

- `memory.py` is the main orchestration layer
- `db.py` owns Kuzu lifecycle, schema bootstrapping, and snapshot save/load
- `llm.py` owns extraction and Cypher generation via the OpenAI SDK
- `cypher.py` is the safety gate before execution
- `ontology.py` persists the evolving schema used to guide future prompts

---

## 4. What Actually Happens on `add()` and `query()`

```mermaid
flowchart TD
    A1["Natural-language fact<br/>e.g. 'Alice works at Acme'"] --> A2["Memory.add()"]
    A2 --> A3["Ontology.to_context_string()<br/>current schema + constraints"]
    A3 --> A4["llm.infer_ontology()<br/>extract entities + relationships"]
    A4 --> A5["build_merge_cypher_groups()<br/>group logical writes"]
    A5 --> A6["sanitize_cypher() + validate_cypher()"]
    A6 --> A7["_execute_cypher_group()<br/>transactional group write"]
    A7 --> A8["Kuzu persists Entity / Relates"]
    A8 --> A9["Ontology updated with labels/types"]
    A9 --> A10["AddResult returned"]

    Q1["Natural-language question<br/>e.g. 'Who works at Acme?'"] --> Q2["Memory.query()"]
    Q2 --> Q3["Ontology.to_context_string()"]
    Q3 --> Q4["llm.generate_cypher(mode='read')"]
    Q4 --> Q5["sanitize + validate"]
    Q5 --> Q6["GraphDB.execute()"]
    Q6 --> Q7["Rows returned as list[dict]"]

    style A2 fill:#16213e,stroke:#e94560,color:#fff
    style Q2 fill:#16213e,stroke:#e94560,color:#fff
    style A7 fill:#533483,stroke:#fff,color:#fff
    style Q6 fill:#533483,stroke:#fff,color:#fff
```

### Important current nuance

Most write-oriented CLI behavior now routes through `Memory`, but `cli.py` still has some direct orchestration for read/query formatting. So the package architecture is cleaner than the CLI architecture in a few places.

---

## 5. Persistent State Model

```mermaid
graph TB
    subgraph USERHOME["User home: ~/.clawgraph/"]
        CFG["config.yaml<br/>model, db path, output format"]
        ONT["ontology.json<br/>learned labels + relationship types"]
        DBDIR["data<br/>Kuzu database files"]
    end

    subgraph DBSCHEMA["Logical Graph Schema"]
        ENTITY["Entity<br/>name (PK)<br/>label<br/>created_at<br/>updated_at"]
        REL["Relates<br/>type<br/>created_at"]
        ENTITY -->|"Relates"| ENTITY2["Entity"]
    end

    SNAP["snapshot.tar.gz"] -. backup / restore .-> DBDIR
    ENV[".env in cwd"] -. overrides .-> CFG

    style USERHOME fill:#16213e,stroke:#e94560,color:#fff
    style DBSCHEMA fill:#0f3460,stroke:#e94560,color:#fff
    style SNAP fill:#533483,stroke:#fff,color:#fff
    style ENV fill:#533483,stroke:#fff,color:#fff
```

### Current persistence assumptions

1. Kuzu is the only shipping graph backend right now
2. All entities are stored in a generic `Entity` table rather than domain-specific node tables
3. All relationships are stored in a generic `Relates` table with `type` as data
4. Timestamps are part of the core schema and are exercised by tests
5. Snapshots are a first-class portability mechanism

---

## 6. Interfaces That Exist Today

### Python API

The `Memory` API is the primary product surface.

Current high-value methods:

1. `add()`
2. `add_batch()`
3. `query()`
4. `entities()`
5. `relationships()`
6. `export()`
7. `save_snapshot()`
8. `from_snapshot()`

### CLI

Current CLI covers:

1. `add`
2. `add-batch`
3. `query`
4. `export`
5. `ontology`
6. `config`
7. `--output json` flows for agent-facing usage

### OpenClaw skill

The repo still positions ClawGraph as a persistent memory substrate that can plug into OpenClaw-style agent workflows.

---

## 7. LobsterGym Evaluation Topology

```mermaid
graph TB
    subgraph MOCKS["Deterministic task world"]
        WEB["lobstergym-web :8080<br/>Flask sites<br/>flights / todos / contact / shop"]
        API["lobstergym-api :8090<br/>FastAPI services<br/>weather / calendar / email / notes"]
    end

    subgraph AGENTS["Agents under test"]
        OC1["OpenClaw + ClawGraph"]
        OC2["OpenClaw baseline"]
    end

    subgraph HARNESS["Eval harness"]
        TASKS["tasks.py<br/>task definitions"]
        RUNNER["runner.py<br/>send task -> poll -> verify"]
        REPORT["reports/*.json"]
    end

    RUNNER --> TASKS
    RUNNER --> OC1
    RUNNER --> OC2
    OC1 --> WEB
    OC1 --> API
    OC1 --> MEM1["ClawGraph memory"]
    OC2 --> WEB
    OC2 --> API
    RUNNER --> WEBSTATE["/state endpoints"]
    RUNNER --> APISTATE["/state endpoints"]
    RUNNER --> REPORT

    style MOCKS fill:#16213e,stroke:#e94560,color:#fff
    style AGENTS fill:#0f3460,stroke:#e94560,color:#fff
    style HARNESS fill:#1a1a2e,stroke:#533483,color:#fff
    style OC1 fill:#e94560,stroke:#fff,color:#fff
    style OC2 fill:#533483,stroke:#fff,color:#fff
```

The important point is not just that LobsterGym exists. It is that the repo includes an environment intended to measure whether memory improves agent behavior instead of relying only on anecdotal demos.

---

## 8. Current Constraints

The current repo state has a few important architectural constraints:

1. LLM support is OpenAI-compatible today, not truly provider-generic yet
2. Kuzu is the only production backend today
3. The schema is intentionally generic and simple rather than semantically rich
4. Query generation is LLM-driven and validated, but not deterministic in the way a hand-written query API would be
5. Some repo areas mix product code, evaluation work, and strategy docs in the same workspace

These are not necessarily problems. They are just the present shape of the system.

---

## 9. Mental Model

```mermaid
graph TD
    R["This repo is really 4 things at once"]
    R --> A["1. Python package<br/>local-first graph memory"]
    R --> B["2. CLI<br/>human + agent-facing entry point"]
    R --> C["3. OpenClaw integration<br/>memory substrate for agents"]
    R --> D["4. Evaluation harness<br/>measure memory effects"]

    A --> A1["Store facts as graph memory"]
    A --> A2["Query with natural language"]
    A --> A3["Persist locally, snapshot, export"]

    B --> B1["Rich human output"]
    B --> B2["JSON output for agent workflows"]

    C --> C1["Persistent memory across tasks"]
    C --> C2["Structured recall instead of flat chat history"]

    D --> D1["Mock sites + APIs"]
    D --> D2["Compare with and without ClawGraph"]

    style R fill:#16213e,stroke:#e94560,color:#fff
    style A fill:#e94560,stroke:#fff,color:#fff
    style B fill:#0f3460,stroke:#e94560,color:#fff
    style C fill:#533483,stroke:#fff,color:#fff
    style D fill:#1a1a2e,stroke:#533483,color:#fff
```

---

## Reading Order

If you want to understand the repo quickly, use this order:

1. [README.md](README.md)
2. [src/clawgraph/memory.py](src/clawgraph/memory.py)
3. [src/clawgraph/llm.py](src/clawgraph/llm.py)
4. [src/clawgraph/db.py](src/clawgraph/db.py)
5. [src/clawgraph/cli.py](src/clawgraph/cli.py)
6. [tests/test_memory.py](tests/test_memory.py)
7. [tests/test_cli.py](tests/test_cli.py)
8. [lobstergym/README.md](lobstergym/README.md)
9. [lobstergym/eval/runner.py](lobstergym/eval/runner.py)

That path gives you: framing -> runtime -> persistence -> interface -> tests -> evaluation.
