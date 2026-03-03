# 🦞 LobsterGym

Agent evaluation framework for benchmarking [OpenClaw](https://github.com/openclaw/openclaw) with and without [ClawGraph](https://github.com/clawgraph/clawgraph) memory.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    docker compose up                         │
├────────────┬────────────┬─────────────────┬──────────────────┤
│ lobstergym │ lobstergym │ openclaw        │ eval-runner      │
│ -web       │ -api       │ gateway         │                  │
│ :8080      │ :8090      │ :18789          │                  │
│            │            │ (± clawgraph)   │                  │
│ Mock sites │ Mock APIs  │ Agent under     │ Sends tasks,     │
│ - Flights  │ - Weather  │ test            │ checks state,    │
│ - Todos    │ - Calendar │                 │ scores pass/fail │
│ - Contact  │ - Email    │                 │                  │
│ - Shop     │ - Notes    │                 │                  │
└────────────┴────────────┴─────────────────┴──────────────────┘
                     ▲                 │
                     │   browser/curl  │
                     └─────────────────┘
```

### Components

| Service | Port | Description |
|---------|------|-------------|
| **lobstergym-web** | 8080 | Flask app with mock websites (flights, todos, contact form, e-commerce) |
| **lobstergym-api** | 8090 | FastAPI app with mock REST APIs (weather, calendar, email, notes) |
| **openclaw-clawgraph** | 18789 | OpenClaw gateway with ClawGraph memory skill |
| **openclaw-default** | 18790 | OpenClaw gateway without ClawGraph (baseline) |
| **eval-clawgraph** | — | Eval runner targeting the ClawGraph-enhanced instance |
| **eval-default** | — | Eval runner targeting the default instance |

## Quick Start

```bash
# 1. Set your API key
export OPENAI_API_KEY="sk-..."

# 2. Start the infrastructure
docker compose -f lobstergym/docker-compose.yml up -d \
  lobstergym-web lobstergym-api openclaw-clawgraph

# 3. Run the ClawGraph eval
docker compose -f lobstergym/docker-compose.yml run eval-clawgraph

# 4. Compare against default (no ClawGraph)
docker compose -f lobstergym/docker-compose.yml up -d openclaw-default
docker compose -f lobstergym/docker-compose.yml run eval-default

# 5. View reports
cat lobstergym/reports/eval-clawgraph.json
cat lobstergym/reports/eval-default.json
```

## Tasks

12 evaluation tasks across 4 categories:

| Category | Task ID | Difficulty | Description |
|----------|---------|------------|-------------|
| browser | `browser-todo-add` | easy | Add a single todo item |
| browser | `browser-todo-multi` | medium | Add 3 todos, mark 1 done |
| browser | `browser-flight-book` | medium | Search & book cheapest flight |
| browser | `browser-contact-form` | medium | Multi-step contact form |
| browser | `browser-shop-checkout` | hard | Add items to cart & checkout |
| api | `api-weather-check` | easy | Query weather for 2 cities |
| api | `api-email-read` | easy | Read unread emails |
| api | `api-calendar-schedule` | medium | Check calendar & schedule event |
| api | `api-email-reply` | medium | Read email & send reply |
| api | `api-notes-organize` | hard | Create notes, update existing |
| memory | `memory-store-recall` | easy | Store & recall fact via ClawGraph |
| multi | `multi-email-calendar-memory` | hard | Email + calendar + memory pipeline |

### Running specific tasks

```bash
# Single task
docker compose -f lobstergym/docker-compose.yml run eval-clawgraph \
  bash -c "python -m lobstergym.eval.runner --profile clawgraph --task browser-flight-book"

# By category
docker compose -f lobstergym/docker-compose.yml run eval-clawgraph \
  bash -c "python -m lobstergym.eval.runner --profile clawgraph --category api"

# By difficulty
docker compose -f lobstergym/docker-compose.yml run eval-clawgraph \
  bash -c "python -m lobstergym.eval.runner --profile clawgraph --difficulty easy"

# List all tasks
python -m lobstergym.eval.runner --list
```

## How It Works

### Verification

Each task has deterministic checks against `/state` endpoints:

```
Agent instruction: "Book the cheapest SFO→JFK flight"
                      │
                      ▼
               OpenClaw agent
            (browser automation)
                      │
                      ▼
              lobstergym-web
           (processes booking)
                      │
                      ▼
          GET /flights/state → {
            "bookings": [{
              "flight_id": "FL200",    ← cheapest
              "passenger_name": "..."
            }]
          }
                      │
                      ▼
             eval harness checks:
             ✓ bookings.length == 1
             ✓ bookings[0].flight_id == "FL200"
             ✓ bookings[0].passenger_name contains "Molty"
```

### Comparison Flow

```
┌─────────────────────┐    ┌─────────────────────┐
│  OpenClaw + ClawGraph│    │  OpenClaw (default)  │
│  (memory-enhanced)  │    │  (no graph memory)   │
└────────┬────────────┘    └────────┬─────────────┘
         │ same tasks              │ same tasks
         ▼                         ▼
┌─────────────────────┐    ┌─────────────────────┐
│ eval-clawgraph.json │    │  eval-default.json   │
│ score: 10/12 (83%)  │    │  score: 8/12 (67%)   │
└─────────────────────┘    └──────────────────────┘
                  │          │
                  ▼          ▼
              Compare: does ClawGraph help?
```

## Mock Services

### lobstergym-web (Browser Scenarios)

| Route | Description |
|-------|-------------|
| `/flights` | Flight search → results → booking form → confirmation |
| `/todos` | CRUD todo list |
| `/contact` | Two-step contact form |
| `/shop` | Product listing → cart → checkout |
| `POST /reset` | Reset all state |
| `/health` | Health check |
| `/<scenario>/state` | State inspection (eval harness) |

### lobstergym-api (API Scenarios)

| Route | Description |
|-------|-------------|
| `GET /weather/{city}` | Current weather |
| `GET/POST /calendar/events` | Calendar CRUD |
| `GET /email/inbox` | Email inbox |
| `POST /email/send` | Send email |
| `GET/POST/PATCH/DELETE /notes` | Notes CRUD |
| `POST /reset` | Reset all state |
| `/health` | Health check |
| `/<service>/state` | State inspection (eval harness) |

## CI Integration

```yaml
# .github/workflows/eval.yml
name: LobsterGym Eval
on:
  pull_request:
    paths: ['src/**', 'skills/**']

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run eval
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          docker compose -f lobstergym/docker-compose.yml up -d \
            lobstergym-web lobstergym-api openclaw-clawgraph
          sleep 30  # wait for gateway
          docker compose -f lobstergym/docker-compose.yml run eval-clawgraph

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: eval-report
          path: lobstergym/reports/eval-clawgraph.json
```

## Development

```bash
# Run web app locally (no Docker)
cd lobstergym/web && pip install -r requirements.txt && python app.py

# Run API locally
cd lobstergym/api && pip install -r requirements.txt && uvicorn app:app --port 8090

# Run eval harness locally (needs services + openclaw running)
pip install requests
python -m lobstergym.eval.runner --list
```
