# CLAUDE.md: OptiServe v2 rules

> Claude Code reads this file automatically. It is the single source of truth for **how** we build.
> **What** we build, and in which order, is in `OPTISERVE_V2_PLAN.md`. If the two disagree, this file wins.
> `CODE.md` and `PROMPTS.md` describe v1 (the hackathon version) and are legacy reference only. Do not follow them.

## 1. Product principles (never break these)

1. **Real data only.** OptiServe shows only metrics collected from real servers: the OptiServe agent or a connected cloud account. No synthetic scenarios, sample datasets or fake numbers anywhere a user can see. Fixtures are allowed **only** in `backend/tests/fixtures/`.
2. **Empty is honest.** With no data, show a friendly empty state that tells the user exactly how to connect a server. Never fill space with placeholders that look like data.
3. **Copilot, not autopilot.** OptiServe never changes infrastructure without a human clicking **Approve**. Every action is logged with who approved it, what changed, and the result.
4. **Safety before savings.** Guardrails (§7) run before every recommendation and again before every action. A blocked action shows the reason in plain words.
5. **Simple first.** A first-time visitor must understand the Home screen in 5 seconds. Plain words, few numbers, one obvious next step (§9).
6. **Prove it.** Every saving shown must be traceable to a real action (instances removed × hours × price). Forecast accuracy is measured on real outcomes and shown.

## 2. Repository layout (keep exactly this)

```
optiserve/
  CLAUDE.md                 # this file
  OPTISERVE_V2_PLAN.md      # product spec + build prompts
  README.md
  docker-compose.yml
  legacy/                   # v1 Streamlit app, moved here, untouched, not run
  backend/
    app/
      main.py               # FastAPI app, routers, CORS, startup jobs
      config.py             # pydantic-settings; reads .env
      db.py                 # SQLModel engine/session (SQLite by default, Postgres via DATABASE_URL)
      models.py             # tables (§4)
      auth.py               # single-admin login, JWT
      api/                  # routers: auth, ingest, servers, groups, forecast, recommendations, actions, connections, stats
      connectors/
        agent.py            # agent tokens, ingest validation
        aws.py              # CloudWatch + EC2 + Auto Scaling read
      engine/               # pure logic, no I/O: profiler, forecaster, planner, guardrails, explainer, accuracy, pricing
      actions/
        executor.py         # runs approved actions, verifies outcome
        aws_actions.py      # set ASG desired capacity, stop/start instance
      jobs/
        scheduler.py        # APScheduler jobs (§6)
    tests/
      fixtures/             # the ONLY place sample data may exist
      test_*.py
    requirements.txt
    .env.example
  agent/
    optiserve_agent.py      # single-file collector (psutil)
    install.sh              # one-line installer
    README.md
  frontend/                 # Vite + React + TypeScript + Tailwind
    src/
      api/                  # typed client + react-query hooks
      components/           # design-system components
      pages/                # Connect, Home, Servers, ServerDetail, Activity, Settings, Login
      lib/                  # format helpers (₹, %, time), icons
  demo/
    demo_app/               # tiny real web app that counts requests (for the live demo)
    loadgen.py              # real HTTP load generator
    aws_setup.md            # step-by-step AWS setup for the demo
    iam_policy.json         # least-privilege policy
```

## 3. Allowed dependencies (nothing else without asking)

- **Backend:** fastapi, uvicorn[standard], sqlmodel, pydantic-settings, apscheduler, boto3, pandas, numpy, pyjwt, bcrypt, httpx. **Tests:** pytest, pytest-asyncio, moto[all], freezegun.
- **Agent:** psutil, requests (Python 3.9+, must run on Amazon Linux 2023 and Ubuntu 22.04+).
- **Frontend:** react, react-dom, react-router-dom, @tanstack/react-query, tailwindcss, recharts, framer-motion, lucide-react, clsx. Dev: vite, typescript, eslint, vitest, @testing-library/react.
- **Demo app:** fastapi, uvicorn.

## 4. Data model (SQLModel tables; UTC timestamps everywhere)

| Table | Key fields |
|---|---|
| `Connection` | id, kind (`agent`/`aws`), name, region, status (`ok`/`error`), last_sync_at, error_message. AWS keys are never stored in the DB: they come from the environment or an IAM role |
| `Group` | id, name, provider (`agent`/`aws`), asg_name (nullable), min_size, max_size, desired, managed (bool: has tag `optiserve:managed=true`) |
| `Server` | id, group_id, name, provider, external_id (EC2 instance id or agent host id), region, instance_type, hourly_cost_usd, state (`running`/`stopped`/`unknown`), last_seen_at |
| `MetricPoint` | server_id, ts, cpu_pct, mem_pct (nullable), net_in_kbps, net_out_kbps, disk_pct (nullable), requests_per_min (nullable). Index (server_id, ts) |
| `Forecast` | id, group_id, created_at, horizon (`short`/`plan`), points_json (ts, expected, low, high), method |
| `Recommendation` | id, group_id, server_id (nullable), kind (`scale_up`/`scale_down`/`stop_idle`/`hold`), from_count, to_count, reason, savings_month_inr, confidence (0–1), status (`pending`/`approved`/`rejected`/`blocked`/`executing`/`done`/`failed`/`expired`), blocked_reason, created_at, expires_at |
| `ActionLog` | id, recommendation_id, approved_by, approved_at, executed_at, finished_at, result (`done`/`failed`/`dry_run`), details_json, realized_savings_inr |
| `AgentToken` | id, token_hash, label, created_at, revoked |

Retention: raw `MetricPoint` 14 days at full resolution, then downsample to 5-minute averages (job in §6).

## 5. Data sources

- **Agent** (`agent/optiserve_agent.py`): every 10 s, POST `/api/ingest` with header `Authorization: Bearer <agent token>` and a body of server identity + metrics. On EC2 it reads instance-id, type and region from instance metadata (IMDSv2) so it links to the AWS record. It buffers up to 10 minutes offline and retries with backoff.
- **AWS** (`connectors/aws.py`), read-only calls: `ec2:DescribeInstances`, `ec2:DescribeInstanceStatus`, `autoscaling:DescribeAutoScalingGroups`, `cloudwatch:GetMetricData`. Metrics: CPUUtilization, NetworkIn/Out per instance; RequestCount per ALB target group if present. On first connect, **backfill 14 days** of hourly history so forecasts work immediately. Memory comes only from the agent (CloudWatch has no memory metric without its own agent): say so in the UI.
- **Prices:** `engine/pricing.py` holds an editable table of on-demand USD/hour for common instance types, with a comment "defaults, verify against the AWS pricing page". The USD→INR rate lives in config. Users can override the price per server in Settings.

## 6. Background jobs (APScheduler, in-process)

| Job | Every | Does |
|---|---|---|
| `sync_aws` | 1 min (live mode) / 5 min | inventory + latest metrics |
| `run_engine` | 1 min | profile → short forecast → plan → guardrails → upsert recommendations (one pending per group; expire stale ones after 15 min) |
| `plan_forecast` | 1 h | 7-day hourly forecast when ≥ 7 days of history exist |
| `verify_actions` | 15 s | poll executing actions until done/failed (timeout 10 min) |
| `score_accuracy` | 5 min | compare past forecasts with actuals |
| `downsample` | daily | retention (§4) |

**Live mode** (`LIVE_MODE=true`) shortens analysis windows so a live demo reacts in minutes: idle = 10 min below threshold instead of 7 days; cooldown 3 min instead of 15. It is real data with shorter windows, and the UI shows a small "Live mode" badge. Never fake anything.

## 7. Engine rules (pure functions in `backend/app/engine/`, no DB or network)

- **Demand unit:** group CPU demand = Σ cpu_pct / 100 (in "server-equivalents"). Memory is the same when available. Plan on whichever is higher (the resource that runs out first).
- **Short forecast (next 60 min, 1-min steps):** Holt linear smoothing on the last 60 min + band = ±z × residual std. **Plan forecast (7 days hourly):** hour-of-week profile + trend (reuse the v1 forecaster) when ≥ 7 days of data; otherwise state "Learning: N of 7 days collected".
- **Servers needed:** `ceil(high / target_util)`, where target_util comes from the risk setting (cost 0.85 ↔ safe 0.55; default 0.70).
- **Idle server:** p95 CPU < 5% and network < 50 kbps over the idle window → `stop_idle` recommendation (only if its group keeps ≥ min servers).
- **Guardrails** (each returns pass/adjusted/blocked + a plain message):
  1. min servers (≥ group min, ≥ 1)
  2. max servers (≤ group max)
  3. scale up early: capacity needed within lead time (5 min live / 30 min normal) triggers scale_up now
  4. step limit: remove at most 1 server per action
  5. cooldown since the last action on the group
  6. health: any server with failed EC2 status checks, mem > 90% or no data for 3 min → block scale-down
  7. low data: < 15 min (live) / < 24 h (normal) of data → hold
  8. low confidence: band wider than 100% of expected → hold
  9. **managed tag required:** actions only on groups/servers tagged `optiserve:managed=true`; otherwise "recommendation only"
- **Explainer:** one or two sentences, no jargon. E.g. "CPU will reach 88% in about 6 minutes. Add 1 server now so it's ready in time."
- **Accuracy:** % = 100 − WAPE over the last 24 h of short forecasts.

## 8. Actions (backend/app/actions)

- Only `approved` recommendations run. Re-run guardrails right before executing; if now blocked → status `blocked`, nothing runs.
- `scale_up` / `scale_down` → `autoscaling:SetDesiredCapacity` (within min/max). `stop_idle` → `ec2:StopInstances` (never terminate). Agent-only servers: recommendation only, no execution.
- `DRY_RUN=true` is the default in `.env.example`: it logs what would happen, result `dry_run`. Real execution needs `DRY_RUN=false` **and** the managed tag.
- Verify the outcome by polling, record it in ActionLog, then compute realized savings: removed servers × hours since action × hourly price (kept up to date by a job).

## 9. UI rules (simple but bold)

- **Pages:** Login → Connect (onboarding) → **Home** → Servers → Server detail → Activity → Settings. Top nav: Home, Servers, Activity, Settings. Nothing else.
- **Home in 5 seconds:** one headline sentence ("Your servers are 23% busy. You can save ₹4,200/month."), the live fleet, the next-24-hour "capacity weather", the copilot feed. That's all.
- **Per card:** max 3 numbers, every number has a word next to it, one primary button.
- **Language:** no jargon in the UI. Use "busy", "idle", "add a server", "stop this server", "OptiServe is learning". Technical detail goes behind "Details".
- **Signature elements:**
  - **Live fleet:** each server is a tile that "breathes" (subtle pulse) with colour by load (calm blue → amber → red); idle tiles look asleep (dim + "zZ").
  - **Capacity weather:** the next 24 h (or 60 min in live mode) as a strip of weather icons: sun = quiet, cloud = normal, storm = peak, with a time label.
  - **Copilot feed:** recommendation cards with one sentence, impact (₹ or risk avoided), and Approve / Not now. Approving shows progress (Approved → Changing… → Done ✓) in real time.
  - **Savings counter:** an animated counter of real ₹ saved since connecting (realized savings only).
- **Look:** light glass style from v1 (white cards, soft shadow, blur header, accent #2563EB), Inter + Outfit fonts, lucide line icons, no emoji. Motion via framer-motion: ≤ 250 ms, respect reduced motion.
- **Updates:** react-query polling (Home and Server detail every 5 s; others 30 s). Show "Updated 3 s ago".
- **States:** every component has loading (skeleton), empty (how to connect) and error (what to do) states.
- **Responsive:** works at 1280–1920 px; usable at 390 px (phone).

## 10. Security

- Secrets only in `.env` (git-ignored); commit only `.env.example`. Never log secrets or tokens.
- AWS: prefer an IAM role (when the backend runs on EC2); otherwise access keys from the environment. Use the least-privilege policy in `demo/iam_policy.json`, where write actions are allowed only on resources tagged `optiserve:managed=true`.
- Agent tokens are stored hashed and can be revoked. Ingest is rate-limited per token.
- One admin login (email + bcrypt hash from env), JWT in an httpOnly cookie. CORS only for the frontend origin.

## 11. Code rules

1. Work only on the files the current prompt names. Don't rewrite finished parts unless asked.
2. Complete, working code: no TODOs, no placeholders, no "rest unchanged".
3. Python: type hints and a one-line docstring on every function; the engine stays pure and unit-tested. TypeScript: `strict` on, no `any`.
4. AWS calls only in `connectors/aws.py` and `actions/aws_actions.py`; tests mock AWS with **moto**. Never call real AWS in tests.
5. Every API route has a pydantic response model and at least one test.
6. After coding: run `pytest -q` (backend) and `npm run build && npm test` (frontend) for the parts you touched; fix until green.
7. Commit at the end of each prompt with a clear message.
8. **Final reply ≤ 10 lines:** files changed, test results, anything blocked or needing a manual step. Never paste whole files back.
