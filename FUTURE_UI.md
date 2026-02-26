# DriftShield — Future UI / Frontend Scope

## Goal

Add a web dashboard so DriftShield can be:
- **Demo'd** live during pitches (show real-time drift alerts on screen)
- **Shared** as a hosted link (deploy once, share URL with anyone)
- **Self-explanatory** (anyone can understand what's happening without reading docs)
- **Pitched** to investors/teams who don't want to read a CLI

---

## Proposed Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Backend API | FastAPI (Python) | Same language as existing codebase, async-native |
| Realtime | WebSockets (FastAPI + `websockets`) | Push drift events to UI the moment they fire |
| Frontend | Next.js 14 + TypeScript | App Router, easy Vercel deploy, great ecosystem |
| UI Components | shadcn/ui + Tailwind | Fast to build, looks professional |
| Charts | Recharts or Tremor | Token usage timelines, drift frequency charts |
| Deploy | Vercel (frontend) + Railway/Render (FastAPI) | Free tiers, instant share links |

---

## Screen-by-Screen Design

### 1. Live Dashboard (Homepage)
- **Active Agents** panel: list of agents currently running (with run_id, start time, token counter ticking up)
- **Drift Feed**: real-time stream of drift events as they fire (like a Twitter feed, newest at top)
  - Color-coded by severity: 🔴 CRITICAL, 🟠 HIGH, 🟡 MED, 🟢 LOW
  - Shows: agent name, detector type, message, timestamp
- **Health Summary**: 3 cards — "Loops today", "Goal drifts today", "Resource spikes today"
- **Token Burn Chart**: sparkline of token usage across last 10 runs per agent

### 2. Agent Detail Page (`/agents/:agent_id`)
- Baseline status badge (CALIBRATED / PENDING with run count)
- Baseline stats table: mean/std for tokens, tools, duration
- Run history timeline: each run as a row with drift event count
- Common action sequences visualization (sequence diagram or sankey)

### 3. Run Detail Page (`/agents/:agent_id/runs/:run_id`)
- Event timeline (chronological): each tool_call, llm_request shown as a step
- Drift events overlaid on the timeline (show exactly when drift fired)
- Token accumulation chart (running total per event)
- Side panel: full DriftEvent details on click

### 4. Alert History Page (`/alerts`)
- Filterable table: by agent, detector, severity, time range
- Export to CSV
- "Acknowledge" button (marks alert as reviewed — needs new DB field)

### 5. Demo Mode
- Pre-loaded fake agent data for pitching without running real agents
- "Replay" button that plays back a simulated drifting agent run in real-time
- Shareable replay URL: `/demo/replay/:scenario_id`
- Scenarios: "stuck search loop", "goal drift after prompt injection", "token explosion"

---

## API Endpoints to Build

```
GET  /api/agents                          → list all agent IDs with last-seen timestamp
GET  /api/agents/:id/baseline             → BaselineStats
GET  /api/agents/:id/runs?limit=20        → list of RunSummary
GET  /api/agents/:id/runs/:run_id/traces  → list of TraceEvent
GET  /api/alerts?agent=&since=&severity=  → list of DriftEvent
GET  /api/stats/summary                   → counts by severity for today
WS   /ws/drift-stream                     → WebSocket: pushes DriftEvent JSON as they fire
WS   /ws/agent-stream/:id                 → WebSocket: pushes TraceEvent JSON for active run
```

---

## FastAPI Backend Implementation Plan

```python
# backend/main.py
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from driftshield.storage import TraceStore

app = FastAPI()
store = TraceStore()

# REST endpoints read from existing SQLite (no schema changes needed)
@app.get("/api/alerts")
async def get_alerts(agent: str = None, since: float = None, limit: int = 50):
    return [e.to_dict() for e in store.get_drift_events(agent_id=agent, since=since, limit=limit)]

# WebSocket: DriftMonitor fires an on_drift callback → puts event in asyncio.Queue
# WebSocket handler reads from queue and pushes to connected clients
connected_clients: list[WebSocket] = []

@app.websocket("/ws/drift-stream")
async def drift_stream(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    try:
        while True:
            await asyncio.sleep(0.1)  # or await queue.get()
    finally:
        connected_clients.remove(ws)
```

The key insight: **the existing SQLite database can be read directly by FastAPI** — no schema changes needed. The UI is purely a read layer on top of the existing storage.

---

## Deployment Architecture (Hosted)

```
User's Python Process                    Cloud
─────────────────────                    ─────
DriftMonitor                             FastAPI (Railway/Render)
  │ saves to SQLite ─────────────────→   reads SQLite (shared volume)
  │                                           │
  └──────────────────────────────────────→   WebSocket push
                                             │
                                        Next.js (Vercel)
                                             │
                                        Browser ← shared URL
```

**Simplest hosted option**:
1. Deploy FastAPI on Railway with SQLite file on mounted volume
2. Deploy Next.js on Vercel, pointing at Railway URL
3. User adds `DRIFTSHIELD_DB_PATH=/data/driftshield.db` env var
4. Share the Vercel URL

**For demo/pitch (local)**:
```bash
uvicorn backend.main:app --port 8000 &
npm run dev  # Next.js on localhost:3000
# Then use ngrok for a shareable URL
ngrok http 3000
```

---

## Implementation Priority

1. **FastAPI + WebSocket backend** (2-3 days) — foundation
2. **Live drift feed + health summary** (1-2 days) — pitch-ready
3. **Agent detail + run timeline** (2-3 days) — explains the system
4. **Demo mode with replay** (1-2 days) — killer demo feature
5. **Alert history + filters** (1 day) — completeness

---

## Folder Structure

```
driftshield-ui/
├── backend/
│   ├── main.py          # FastAPI app
│   ├── routers/
│   │   ├── agents.py
│   │   ├── alerts.py
│   │   └── ws.py        # WebSocket handlers
│   └── requirements.txt
└── frontend/
    ├── app/
    │   ├── page.tsx           # Live dashboard
    │   ├── agents/[id]/
    │   │   ├── page.tsx       # Agent detail
    │   │   └── runs/[run]/
    │   │       └── page.tsx   # Run detail
    │   └── alerts/page.tsx    # Alert history
    ├── components/
    │   ├── DriftFeed.tsx      # Real-time event stream
    │   ├── AgentCard.tsx
    │   ├── RunTimeline.tsx
    │   └── SeverityBadge.tsx
    └── lib/
        └── api.ts             # API client + WebSocket hook
```
