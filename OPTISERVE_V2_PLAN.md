# OptiServe v2: product plan and build prompts

> Rules for **how** to build are in `CLAUDE.md`. This file is **what** to build and **in which order**.

## 1. What changed from v1, and why

| Judges' feedback | v2 answer |
|---|---|
| "Build it like a product" | Real backend + database + login + onboarding + a modern web app; deployable with one command |
| "Connect it to a cloud server and show what happens" | A one-line **agent** for any server, plus an **AWS connector** (CloudWatch, EC2, Auto Scaling). Approved actions **really** scale an Auto Scaling group or stop an idle instance |
| "Sample data and scenarios were a failure" | Removed. Only real metrics. Empty states explain how to connect |
| "The website is too complex" | 4 pages; Home understood in 5 seconds; plain words; one action per card. Bold signature visuals: breathing live fleet, capacity weather, live savings counter |

**New one-line pitch:** *"Connect your servers in 2 minutes. OptiServe watches real usage, warns you before you run short, finds servers you're wasting money on, and fixes it with one click, only when you approve."*

## 2. How it works

```
 Your servers                         OptiServe backend (FastAPI)                     Web app (React)
 ─────────────                        ───────────────────────────                     ───────────────
 Any VM + agent ──(every 10 s)──▶  /api/ingest ─┐                                    Home: live fleet,
                                                ├─▶ Metrics DB ─▶ Engine (1 min):     weather, copilot feed
 AWS account ◀──(read every 1–5 min)── AWS sync ┘      profile → forecast → plan       Servers / detail
   CloudWatch, EC2, Auto Scaling                       → guardrails → recommendations  Activity: proof
        ▲                                                       │
        └──── SetDesiredCapacity / StopInstances ◀── Executor ◀─┴── human clicks Approve
```

## 3. Features (v2 scope)

**Must-have (the product)**
1. **Login + onboarding "Connect"**: two options. (a) *Install agent*: shows a copy-paste one-liner with a fresh token; the server appears live within 10 s. (b) *Connect AWS*: region + credentials check; finds instances and Auto Scaling groups; backfills 14 days of history.
2. **Home**: headline sentence, live fleet tiles, capacity weather, copilot feed, savings counter.
3. **Servers**: list with live load, state, cost/month, status (Busy / Normal / Idle / Unhealthy), managed or not.
4. **Server / group detail**: live chart (last 60 min) + forecast band + capacity line; "What OptiServe sees" in plain words; safety checks.
5. **Recommendations + human approval**: Approve / Not now → real action (or dry-run) → live progress → verified result.
6. **Activity (proof)**: timeline of actions with before/after mini-charts, realized ₹ saved, forecast accuracy %.
7. **Settings**: connections, agent tokens, risk setting (Cost ⟷ Safe), live mode, dry-run switch, prices.

**Signature "wow" elements:** breathing live fleet · capacity weather strip · real-time approval progress · animated real-savings counter.

**Stretch (only after everything works):** "Ask OptiServe" chat (Claude API) answering "why?" questions from real data · Slack/email alerts · GCP/Azure connectors · scheduled weekly plan report.

**Removed from v1:** synthetic scenarios, scenario picker, Time Machine on fake data (replaced by real accuracy + real before/after), Graveyard page (idle servers now show as "asleep" tiles plus a stop recommendation).

## 4. Live demo for judges (the target the build aims at)

Set-up beforehand: an AWS Auto Scaling group (`optiserve-demo`, t3.micro, min 1 / max 3 / desired 1, tagged `optiserve:managed=true`) running `demo/demo_app` + the agent; one extra lone EC2 instance left idle (`forgotten-test-box`, tagged); backend deployed; `LIVE_MODE=true`, `DRY_RUN=false`.

1. **Connect (30 s):** open OptiServe → Connect AWS → the instances and the group appear; the history chart fills from CloudWatch.
2. **Live fleet:** tiles breathing calmly; the idle box looks asleep.
3. **Make a real spike:** run `python demo/loadgen.py --url <demo app> --rps 200 --minutes 8`. Judges watch the tile go amber → red and the weather strip turn to storm.
4. **Copilot warns:** "CPU will reach 90% in ~6 minutes. Add 1 server now." → **Approve** → progress: Approved → Changing… → Done ✓. Open the AWS console: desired capacity 1 → 2, a new instance launching. Its tile appears in OptiServe when its agent starts.
5. **Waste:** "forgotten-test-box has been idle. Stop it to save ₹X/month." → Approve → the instance stops in AWS.
6. **Load ends:** OptiServe recommends scaling back down after the cooldown → Approve → desired 2 → 1.
7. **Proof:** Activity shows each action, who approved it, the result, the real ₹ saved since connecting and the forecast accuracy.

**Cost safety:** t3.micro instances, a few hours only. Delete everything after (see `demo/aws_setup.md` cleanup). Set an AWS billing alarm.

## 5. Build prompts (12)

**How to run them:** put `CLAUDE.md` and this file in the project root. Run the prompts in order in Claude Code, `/clear` between prompts, check the "Done when" line before moving on. If something fails, reply only with the error lines + "fix with minimal changes". If an engine or API contract needs to change, update `CLAUDE.md` in the same commit.

---

### P0: Save v1 and reorganise
```
Read CLAUDE.md and OPTISERVE_V2_PLAN.md.
1. git push any unpushed commits; tag the current state v1-hackathon; push tags; create and switch to branch v2.
2. Move the whole v1 Streamlit app (app.py, ui/, .streamlit/, engine/, tests/, CODE.md, PROMPTS.md, UI_UPGRADE.md, README.md) into legacy/ with git mv. Do not modify it.
3. Create the empty v2 layout from CLAUDE.md §2 (folders + minimal __init__.py / placeholder package.json only where needed), .gitignore (.env, node_modules, __pycache__, *.db, dist), backend/.env.example with every setting from CLAUDE.md (DATABASE_URL, JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD_HASH, AWS_REGION, LIVE_MODE, DRY_RUN=true, USD_INR, FRONTEND_ORIGIN).
Commit "v2: reorganise, v1 moved to legacy". Reply ≤6 lines.
```
**Done when:** `legacy/` contains v1, the new folders exist, and you're on branch `v2`.

### P1: Backend skeleton, database, login
```
Follow CLAUDE.md §2–4, §10–11. Build backend/app: config.py (pydantic-settings), db.py (SQLModel, SQLite default), models.py (all tables in §4 with indexes), auth.py (single admin, bcrypt, JWT httpOnly cookie; routes /api/auth/login, /api/auth/logout, /api/auth/me), main.py (FastAPI, CORS for FRONTEND_ORIGIN, /api/health, router registration, create tables on startup). Add a small script backend/scripts/hash_password.py to produce ADMIN_PASSWORD_HASH.
Tests: login ok/fail, protected route needs auth, health. Run pytest. Commit "backend: skeleton + auth". Reply ≤8 lines.
```
**Done when:** `uvicorn app.main:app --reload` runs, `/api/health` is OK, and login works.

### P2: Agent and ingest
```
Follow CLAUDE.md §4, §5 (Agent), §10. Build:
- backend: AgentToken create/list/revoke API (/api/agent-tokens), POST /api/ingest (Bearer agent token, validate, upsert Server by external_id, insert MetricPoint, rate-limit per token, update last_seen_at). Auto-create Group "Ungrouped" for agent servers.
- agent/optiserve_agent.py: every 10 s collect cpu_pct, mem_pct, net in/out kbps, disk_pct (psutil); optional requests_per_min by reading a local counter URL (--requests-url); detect EC2 via IMDSv2 (instance-id, type, region, ASG name from tags if available) else use hostname; buffer offline up to 10 min; retry with backoff; --url and --token args or env.
- agent/install.sh: installs python deps, writes a systemd service, starts it (args: URL, TOKEN, optional REQUESTS_URL). agent/README.md.
Tests: ingest happy path, bad token, rate limit, server upsert. Run pytest. Commit "agent + ingest". Reply ≤8 lines.
```
**Done when:** running the agent on your laptop against the local backend creates a Server, and MetricPoints arrive every 10 s.

### P3: AWS connector
```
Follow CLAUDE.md §5 (AWS), §6, §10. Build connectors/aws.py: validate credentials (sts get_caller_identity), list instances (+ state, type, tags, status checks), list Auto Scaling groups (+ min/max/desired, instances, managed tag), fetch metrics with GetMetricData (CPUUtilization, NetworkIn/Out; ALB RequestCount if target groups exist), backfill 14 days hourly on first connect, then incremental 1-min (live) / 5-min. Map to Connection/Group/Server/MetricPoint; agent and AWS data for the same instance merge on instance-id (agent wins for mem/disk).
API: POST /api/connections/aws (region, optional keys → stored only in process env, never DB), GET /api/connections, POST /api/connections/{id}/sync.
Also write demo/iam_policy.json (read actions + SetDesiredCapacity/StopInstances/StartInstances only on resources tagged optiserve:managed=true) and demo/aws_setup.md (IAM user or role, launch template t3.micro with user-data installing demo app + agent, ASG optiserve-demo min1 max3 desired1 with tag, one lone tagged idle instance, billing alarm, full cleanup steps).
Tests with moto. Run pytest. Commit "aws connector". Reply ≤8 lines.
```
**Done when:** connecting a real AWS account lists its instances and group, and their CPU history appears in the DB.

### P4: Engine on real data
```
Follow CLAUDE.md §7. Port the useful parts of legacy/engine into backend/app/engine as PURE functions working on DataFrames from MetricPoint: profiler (Busy/Normal/Idle/Unhealthy + idle detection), forecaster (short: Holt linear 60 min + band; plan: hour-of-week + trend for 7 days when ≥7 days data, else "learning" status), planner (servers needed from high band and risk), guardrails (all 9 rules, plain messages), explainer (1–2 plain sentences), accuracy (WAPE-based %), pricing (editable USD/hour table + INR). No DB or network imports in engine/.
Use fixtures in backend/tests/fixtures (generated in tests only) to test: rising load → scale_up before threshold within lead time; idle server → stop_idle; unhealthy → scale-down blocked; low data → hold; unmanaged group → recommendation only; step limit and cooldown. Run pytest. Commit "engine v2". Reply ≤8 lines.
```
**Done when:** all engine tests pass, and the engine has no I/O imports.

### P5: Jobs, recommendations, approval, actions
```
Follow CLAUDE.md §6–8. Build jobs/scheduler.py (all jobs in §6, LIVE_MODE aware), recommendation upsert/expiry, APIs: GET /api/recommendations, POST /api/recommendations/{id}/approve (records approver), /reject, GET /api/actions, GET /api/stats (headline numbers: avg busy %, servers, monthly cost, potential savings, realized savings, accuracy).
actions/executor.py + aws_actions.py: re-check guardrails, then SetDesiredCapacity or StopInstances (never terminate), honour DRY_RUN, poll until done/failed (verify_actions job), write ActionLog, compute realized savings over time.
Tests with moto: approve → desired capacity changes; dry-run → nothing changes in AWS; blocked at execution time → no call made; unmanaged → refused. Run pytest. Commit "approval + actions". Reply ≤8 lines.
```
**Done when:** approving a recommendation (via the API) really changes desired capacity in AWS (with `DRY_RUN=false`), and ActionLog shows the result.

### P6: Frontend foundation
```
Follow CLAUDE.md §9. Create frontend with Vite + React + TS (strict) + Tailwind. Build: design tokens (light glass, accent #2563EB, Inter/Outfit), layout (glass top bar: logo, nav Home/Servers/Activity/Settings, live-mode badge, user menu), typed API client + react-query hooks for every backend route, auth flow (Login page, protected routes), formatting helpers (₹, %, "3 s ago"), shared components: Card, StatNumber (number + word), Button, Pill, Skeleton, EmptyState, ErrorState, Toast. Vite proxy /api → backend.
Pages as simple shells with correct empty states. Run npm run build and npm test. Commit "frontend foundation". Reply ≤8 lines.
```
**Done when:** you can log in and navigate, and every page shows a clean empty state.

### P7: Connect (onboarding)
```
Follow CLAUDE.md §9. Build the Connect page (also shown automatically when there are no servers): two big choice cards.
(a) Install agent: generate token → show a copy-paste install command with copy button → "Waiting for your server…" live indicator → success animation when the first metric arrives → button "Go to Home".
(b) Connect AWS: region select + optional keys (with note that an IAM role is preferred) → Test connection → shows found instances/groups and backfill progress → success.
Run build + tests. Commit "onboarding". Reply ≤6 lines.
```
**Done when:** a brand-new user can connect a real server from the browser without reading docs.

### P8: Home (the 5-second screen)
```
Follow CLAUDE.md §9 exactly. Build Home:
1. Headline sentence from /api/stats ("Your servers are 23% busy. You can save ₹4,200/month.") + animated real-savings counter.
2. Live fleet: tile per server grouped by Group; breathing pulse speed and colour by CPU (calm blue → amber → red); idle = dim "asleep" with zZ; unhealthy = red outline + icon; hover shows name, CPU, memory, cost; click opens detail.
3. Capacity weather: next 24 h (60 min in live mode) from the forecast as weather icons (sun/cloud/storm) with time labels and a one-line summary ("Storm expected at 18:00").
4. Copilot feed: recommendation cards (one sentence, impact, Approve / Not now); approving shows live progress Approved → Changing… → Done ✓ (poll), blocked cards show the reason.
Polling 5 s, "Updated Xs ago". Skeleton/empty/error states. Check at 1280, 1920 and 390 px. Run build + tests. Commit "home". Reply ≤6 lines.
```
**Done when:** a stranger understands the Home screen in 5 seconds, and the tiles move with real load.

### P9: Servers, detail, Activity, Settings
```
Follow CLAUDE.md §9. Build:
- Servers: table/list with live busy %, state, ₹/month, status pill, managed badge, search + filter (Busy/Idle/Unhealthy).
- Server/Group detail: live 60-min chart with forecast band and capacity line, "What OptiServe sees" (plain sentences), safety checks list, current recommendation with Approve.
- Activity: timeline of ActionLog (who, when, what, result) with before/after mini-chart, realized ₹ saved, forecast accuracy %.
- Settings: connections (status, sync now, remove), agent tokens (create/revoke), risk slider "Save more ⟷ Stay safe" with one-line plain explanation, live mode and dry-run switches (with warnings), price overrides.
Run build + tests. Commit "servers, activity, settings". Reply ≤6 lines.
```
**Done when:** every page works with real data, and Activity proves each action.

### P10: Demo kit
```
Follow CLAUDE.md §2 (demo/). Build demo/demo_app (FastAPI: /, /work?ms=50 doing real CPU work, /metrics returning requests_per_min counter) with a systemd install script; demo/loadgen.py (async HTTP load: --url --rps --minutes, ramp up/down, live console output). Update demo/aws_setup.md user-data so each new ASG instance auto-installs demo_app + agent pointing to the backend URL. Add a "Demo checklist" section to README (before / during / cleanup). Commit "demo kit". Reply ≤6 lines.
```
**Done when:** running loadgen against the ASG makes CPU rise in OptiServe within about a minute.

### P11: Deploy
```
Create Dockerfiles for backend and frontend (frontend served by nginx with /api proxied) and docker-compose.yml (backend, frontend, volume for SQLite; Postgres optional profile). Write README deploy guide for: (a) single EC2 instance with docker compose + IAM role (recommended for the demo), (b) local dev with a cloudflared/ngrok tunnel so cloud agents can reach a laptop. Health checks, restart policies, env from .env. Commit "deploy". Reply ≤6 lines.
```
**Done when:** `docker compose up` runs the full product, and a cloud agent can reach it at a public URL.

### P12: Polish, end-to-end check, README
```
Final pass, minimal changes: run all backend and frontend tests; run the full demo flow from OPTISERVE_V2_PLAN.md §4 against real AWS in DRY_RUN=true then DRY_RUN=false; fix anything broken; verify no synthetic data is reachable from the UI; verify every page has loading/empty/error states; accessibility pass (contrast, focus, alt text, reduced motion). Rewrite README: pitch, screenshots placeholders list, architecture, quick start, connect guide, security notes, demo script, roadmap. Commit "v2 ready". Reply ≤10 lines with anything not verified.
```
**Done when:** the full live demo runs end to end on real AWS.

---

## 6. Milestones (check after each)

| After | You can show |
|---|---|
| P2 | Your laptop as a live server in the database |
| P3 | A real AWS account's servers and 14-day history |
| P5 | One approve click that really scales AWS (via the API) |
| P8 | The Home screen with a live fleet: the core demo is ready |
| P10 | The full judge demo with a real load spike |
| P12 | Deployed, documented product |

## 7. Answers ready for judges (v2)

- **"Is the data real?"** Yes: live from the agent and CloudWatch. There's no sample data in the product.
- **"Does it actually change the cloud?"** Yes: after a human approves, it calls AWS Auto Scaling or stops an idle instance, and it only touches resources tagged `optiserve:managed=true`.
- **"Why not just AWS autoscaling?"** Predictive scaling only adds capacity and forecasts about 2 days ahead. Compute Optimizer only suggests sizes from history. OptiServe adds *and* removes, finds idle servers, explains why, waits for approval, and proves savings on real outcomes.
- **"What stops it from breaking production?"** Nine guardrails, dry-run mode, managed tags, a one-server step limit, cooldowns, health checks, and human approval.
