# ClawGraph — Launch Plan

> Last updated: 2026-03-03
> Target hard launch: v0.2.0 (~March 10-14, 2026)

---

## Timeline

### Phase 0: Prep (March 3-5) — "Build in public"

**Identity & accounts:**
- [ ] Create new GitHub account with brand handle (e.g., `clawgraphai`)
- [ ] Transfer `clawgraph/clawgraph` org ownership to new account
- [ ] Keep personal account as admin collaborator (never public-facing)
- [ ] Update PyPI maintainer to new handle's email
- [ ] Verify X handle @clawgraphai is active and connected
- [ ] Set up Bluesky: @clawgraphai.bsky.social
- [ ] Set up Discord server (or channel in an AI agents community)

**Soft launch posts (X/Bluesky):**
- Day 1 post: "Building an open-source graph memory layer for AI agents. No server needed — embedded Kùzu DB, works with any LLM. Early alpha. github.com/clawgraph/clawgraph"
- Day 2 post: Show a code snippet (3 lines: import, add, query)
- Day 3 post: "Why graph memory > vector memory for agents" — thread with the comparison table
- Pin the day 1 post

**Codebase:** Agents are shipping F02-F05 + quick wins overnight. Review and merge PRs.

### Phase 1: v0.2.0 Release (March 10-12) — "The headline"

**Features that must ship:**
- F01: Hybrid retrieval (graph + vector) — THE headline feature
- F05: Tool-use function definitions — instant framework integration
- F02: Confidence scoring — shows depth
- Quick wins merged (CI badge, CONTRIBUTING.md, stats/version commands)

**Release checklist:**
- [ ] Bump version to 0.2.0 in pyproject.toml
- [ ] Update README with new features, demo GIF, benchmarks
- [ ] Publish to PyPI: `python -m build && twine upload dist/*`
- [ ] Create GitHub Release v0.2.0 with changelog
- [ ] Record demo GIF (asciinema or VHS): add facts → query → show graph
- [ ] Write blog post for clawgraph.ai

### Phase 2: Hard Launch (March 12-14) — "Show HN"

**Day 0 (Wednesday):**
- Final review of README, blog post, demo GIF
- Dry-run the Show HN title and description
- Queue social posts

**Day 1 (Thursday, ~9am US Pacific):**
- **Hacker News**: Post "Show HN: ClawGraph – Embedded graph memory for AI agents"
- **Reddit**: r/MachineLearning, r/LocalLLaMA, r/artificial, r/Python
- **X/Bluesky**: Announcement thread
- Monitor comments, respond quickly (first 2-4 hours are critical for HN)

**Day 2-3 (Friday-Saturday):**
- Follow-up posts with benchmark results from LobsterGym
- Cross-post to AI agent community Discords (OpenClaw, LangChain, CrewAI)
- Direct outreach to 5-10 agent framework maintainers

### Phase 3: Sustain (March 15+) — "Build community"

- Weekly X/Bluesky posts showing ClawGraph in action
- Respond to all GitHub issues/discussions within 24 hours
- Ship v0.3.0 (workflow memory) with another launch push
- Conference talk proposals: PyCon, AI Engineer Summit
- Partner with 1-2 agent framework projects for official integration

---

## Messaging

### One-liner
> Open-source graph memory for AI agents. Embedded, no server, `pip install clawgraph`.

### Elevator pitch (30 seconds)
> AI agents forget everything between sessions. Vector stores give you "similar text" but can't answer "who manages Alice?" ClawGraph stores facts as a knowledge graph — entities, relationships, timestamps — in an embedded database. No server, no cloud dependency. pip install it, add facts in natural language, query with natural language. Works with any LLM.

### Show HN post

**Title:** `Show HN: ClawGraph – Embedded graph memory for AI agents (Python, open-source)`

**Body:**
```
Hey HN,

I built ClawGraph because AI agents have a memory problem. Vector stores 
give you "find similar text" but can't answer structured questions like 
"who manages Alice?" or "what tools did I use in yesterday's deploy?"

ClawGraph stores facts as a knowledge graph (entities + relationships) in 
an embedded Kùzu database. No server needed — it works like SQLite for 
graph memory.

    pip install clawgraph

    from clawgraph.memory import Memory
    mem = Memory()
    mem.add("Alice is an engineer at Acme Corp")
    mem.add("Bob manages Alice")
    mem.query("Who works at Acme?")  # → structured results

Key features:
- Natural language in, structured graph out (LLM extracts entities/rels)
- Embedded DB — no Neo4j server, no cloud dependency
- Any LLM via LiteLLM (OpenAI, Anthropic, Ollama, etc.)
- Hybrid retrieval — graph queries + vector similarity fallback
- Idempotent writes (MERGE-based, safe to re-add facts)
- Snapshots for portable memory backups
- Works as an OpenClaw skill for agent frameworks

It's Apache-2.0 licensed. I also built LobsterGym, an eval framework that 
benchmarks agent performance with/without graph memory.

GitHub: https://github.com/clawgraph/clawgraph
PyPI: https://pypi.org/project/clawgraph/
Docs: https://clawgraph.ai/docs

Would love feedback on the API design and what memory features matter most 
for your agent workflows.
```

### Comparison table (for blog post / README)

| | Vector Store | ClawGraph |
|---|---|---|
| Storage | Text chunks → embeddings | Entities → Relationships |
| Query | "Find similar text" | "Who manages Alice?" |
| Structure | Flat | Graph (traversable) |
| Deduplication | Hard | Built-in (MERGE) |
| Multi-hop | Impossible | Natural |
| Server | Usually required | Embedded (like SQLite) |
| LLM at write | No | Yes (entity extraction) |
| LLM at read | No | Yes (Cypher generation) |

---

## Content Calendar

| Date | Platform | Content | Status |
|------|----------|---------|--------|
| Mar 3 | X/Bluesky | "Building open-source graph memory for agents" | Not started |
| Mar 4 | X/Bluesky | Code snippet showing 3-line usage | Not started |
| Mar 5 | X/Bluesky | "Graph vs vector memory" thread | Not started |
| Mar 7 | X/Bluesky | Demo GIF preview | Not started |
| Mar 10 | GitHub | v0.2.0 Release | Not started |
| Mar 10 | PyPI | Publish 0.2.0 | Not started |
| Mar 10 | clawgraph.ai | Blog post: "Why graph memory" | Not started |
| Mar 12 | Hacker News | Show HN post | Not started |
| Mar 12 | Reddit | Cross-posts (4 subreddits) | Not started |
| Mar 12 | X/Bluesky | Launch announcement thread | Not started |
| Mar 13 | X/Bluesky | Benchmark results from LobsterGym | Not started |
| Mar 14 | Discord | Share in AI agent communities | Not started |
| Mar 17 | X/Bluesky | "What we learned from launch week" | Not started |

---

## Metrics to Track

### Week 1 targets (realistic for a niche dev tool)
- **GitHub stars:** 50-200
- **PyPI downloads:** 100-500
- **HN points:** 50+ (front page threshold)
- **GitHub issues from external users:** 5+
- **First external PR:** 1

### Month 1 targets
- **GitHub stars:** 500-1000
- **PyPI weekly downloads:** 200+
- **Discord/community members:** 30+
- **Integration PRs from framework authors:** 1-2

### How to track
- GitHub: Insights tab (traffic, clones, stars)
- PyPI: pypistats.org/packages/clawgraph
- HN: Monitor post directly
- Social: X analytics, Bluesky stats

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| HN post doesn't take off | Reddit + Discord + direct outreach as fallback channels |
| "Just use Mem0" comments | Prepared response: embedded vs hosted, open-source vs closed, no vendor lock-in |
| "Why not just use Neo4j?" | Prepared response: embedded (no server), pip install, designed for agents not DBAs |
| Bug reports flood in | QW09 (better error messages) + quick triage, label as "good first issue" for contributors |
| Someone copies the idea | First-mover advantage, community, eval framework as moat |
| Identity exposure | Brand account is the public face, personal account stays private |

---

## Outreach List

### Agent framework communities (direct outreach)
- OpenClaw Discord/forum
- LangChain Discord (#show-and-tell)
- CrewAI community
- AutoGPT Discord
- Semantic Kernel (Microsoft)

### Influencers / accounts to engage with
- AI agent builders with 5-50k followers on X
- Python open-source maintainers
- "Building in public" accounts

### Potential integration partners
- OpenClaw — already have a skill
- LangChain — MemoryProvider integration
- LlamaIndex — storage backend
- Haystack (deepset) — document store adapter

---

## Post-Launch Priorities

1. **Respond to every HN comment and GitHub issue** — first 48 hours set the tone
2. **Ship fixes fast** — if someone reports a bug, fix it same day
3. **Say thank you** — acknowledge every star, issue, and PR publicly
4. **Write "What I learned" post** — authentic reflection drives second wave
5. **Plan v0.3.0 announcement** — keep momentum with regular releases
