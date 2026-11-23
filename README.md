# OptiServe

**Connect your servers in 2 minutes. OptiServe watches real usage, warns you before you run short, finds servers you're wasting money on, and fixes it with one click, only when you approve.**

- **Real data only.** Numbers come from the OptiServe agent on any Linux server, or from a read-only AWS connection (EC2, Auto Scaling, CloudWatch). With nothing connected, every screen says how to connect instead of showing sample numbers.
- **Copilot, not autopilot.** Every change waits for a person to click **Approve**, passes nine safety checks before it is suggested and again before it runs, and is logged with who approved it and what happened.
- **Proof, not promises.** "Saved" counts only real actions: servers removed × hours since × price. Forecast accuracy is measured against what really happened.

## Screenshots

To add in `docs/screenshots/` (1280 px wide, light theme, taken on the live demo):

1. `connect.png`: the two choices, Install the agent and Connect AWS.
2. `connect-agent-success.png`: the install command, then "web-1 is connected".
3. `home.png`: headline sentence, breathing live fleet, capacity weather, Copilot feed.
4. `home-storm.png`: during the spike, a red tile, a storm in the weather strip, and an "Add 1 server now" card.
5. `approve-progress.png`: Approved → Changing… → Done on a card.
6. `servers.png`: the list filtered to Idle.
7. `server-detail.png`: 60-minute chart with forecast band and capacity line, What OptiServe sees, safety checks.
8. `activity.png`: timeline with before/after mini-charts, ₹ saved and forecast accuracy.
9. `settings.png`: Save more ⟷ Stay safe slider, live mode and dry-run switches, prices.
10. `phone-home.png`: Home at 390 px.

## How it works

```
 Your servers                          OptiServe backend (FastAPI, one process)                 Web app (React)
 ────────────                          ────────────────────────────────────────                 ───────────────
 Any Linux server + agent ──every 10 s──▶ POST /api/ingest ─┐                                    Connect
   (CPU, memory, network, disk,        (Bearer agent token,  │                                    Home: headline, live fleet,
    requests/min from your app)         rate-limited)        ├─▶ SQLite / Postgres ──▶ Engine     capacity weather, Copilot
                                                             │    (MetricPoint)        every min  Servers / Server detail
 AWS account ◀──read every 1–5 min── sync_aws job ───────────┘                         profile    Activity (proof)
   EC2 · Auto Scaling · CloudWatch     (14-day backfill on connect)                     forecast   Settings
        ▲                                                                               plan
        │                                                                               9 guardrails
        └── SetDesiredCapacity / StopInstances ◀── executor ◀── Approve (a person) ◀── suggestion
            (managed tag + DRY_RUN=false only;      re-checks guardrails, verifies the result,
             never terminates)                      writes ActionLog, counts realized savings
```

- **Engine** (`backend/app/engine/`, pure functions, unit-tested): server status (busy / normal / idle / unhealthy), a 60-minute Holt forecast with an uncertainty band, a 7-day hour-of-week forecast once 7 days exist, servers needed = ⌈high band ÷ target busy⌉, nine guardrails (min/max servers, scale up early, step limit, cooldown, health, low data, low confidence, managed tag), and a one- or two-sentence plain explanation.
- **Jobs** (in-process APScheduler): AWS sync, engine every minute, plan forecast hourly, action verification every 15 s, accuracy every 5 min, daily downsampling of data older than 14 days.
- **Live mode** shortens the windows (idle after 10 min instead of 7 days, cooldown 3 min instead of 15) so a demo reacts in minutes. Same real data, and the UI shows a badge.
- **Web app**: React + TypeScript + Tailwind, polling every 5 s on Home and Server detail.

## Quick start (local)

```bash
# Backend (Python 3.11+)
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                          # set JWT_SECRET and ADMIN_EMAIL
.venv/bin/python scripts/hash_password.py     # paste the printed line into .env
.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend (Node 20+), in another terminal
cd frontend && npm install && npm run dev     # http://localhost:5173 (/api is proxied to :8000)
```

Or run everything in containers: `cp .env.example .env`, fill it in, then `docker compose up -d --build` (see [Deploy](#deploy)).

**Tests:** `cd backend && .venv/bin/python -m pytest -q` · `cd frontend && npm run build && npm test` · demo kit: `backend/.venv/bin/python -m pytest -q demo/tests`

## Connect your servers

Sign in. With no servers yet, OptiServe opens **Connect** by itself.

**Install the agent** (any Linux server: Ubuntu 22.04+, Amazon Linux 2023; Python 3.9+):
1. Name the server, then **Create install command**.
2. Check the address: it must be one the server can reach (not `localhost` when the server is elsewhere).
3. Run the copied one-liner on the server. It installs the `optiserve-agent` systemd service.
4. The page waits for the first numbers and shows "*name* is connected" within about 10 seconds.

Optional: give the agent your app's request counter (`--requests-url`, JSON `{"requests_per_min": n}`). On EC2 the agent links itself to the instance through IMDSv2, so agent and AWS data merge (memory comes only from the agent). More: [agent/README.md](agent/README.md).

**Connect AWS** (read-only until you approve a change):
1. Pick the region. Leave the keys empty when OptiServe runs on EC2 with an IAM role (recommended). Otherwise paste access keys: they stay in the backend's memory only.
2. **Test connection** lists the instances and Auto Scaling groups it can see. Nothing is saved yet.
3. **Connect and bring in history** saves the connection and backfills 14 days of hourly CloudWatch data, so forecasts work from day one.
4. OptiServe can act only on groups and instances tagged `optiserve:managed=true`. Everything else gets suggestions only. The least-privilege policy is in [demo/iam_policy.json](demo/iam_policy.json); setup steps are in [demo/aws_setup.md](demo/aws_setup.md).

## Security notes

- **Nothing changes without a person.** Suggestions run only after **Approve**. Guardrails run again right before execution, and a change that is now unsafe is blocked with the reason. `DRY_RUN=true` is the default: it logs what would happen and changes nothing. Turning it off in Settings needs an explicit confirmation.
- **Least privilege.** The IAM policy allows reads everywhere, and `SetDesiredCapacity`, `StopInstances` and `StartInstances` only on resources tagged `optiserve:managed=true`. Terminating instances and deleting groups are explicitly denied. OptiServe never terminates.
- **AWS keys** are never stored in the database or logs. Prefer an IAM role. Keys pasted in Connect live only in the backend process's memory; the connection test doesn't keep them at all.
- **Agent tokens** are random, shown once, stored only as a SHA-256 hash, revocable in Settings, and rate-limited per token on ingest.
- **Login:** one admin (email + bcrypt hash from `.env`), JWT in an httpOnly, SameSite cookie, which becomes secure-only when `FRONTEND_ORIGIN` is `https://`. CORS allows only that origin.
- **Secrets** live only in `.env` (git-ignored); only `.env.example` files are committed. The backend container runs as a non-root user.
- **Exposure:** serve OptiServe over HTTPS (tunnel or ALB) and restrict port 80 to your IP and your agents' network. User-data agent tokens are readable by anyone with `ec2:DescribeInstanceAttribute`, so use a demo-only token and revoke it afterwards.

## Deploy

Two containers, started by [docker-compose.yml](docker-compose.yml):

| Service | What it does | Health check | Restart |
|---|---|---|---|
| `backend` | FastAPI API + background jobs (one worker on purpose: the jobs run inside it). SQLite on the `optiserve-data` volume. | `GET /api/health` every 15 s | `unless-stopped` |
| `frontend` | nginx serving the app on port 80 and forwarding `/api/` to the backend (agents use this too). | `GET /healthz` every 15 s | `unless-stopped` |
| `postgres` | optional, only with `--profile postgres` | `pg_isready` | `unless-stopped` |

All settings come from one `.env` file next to `docker-compose.yml` ([.env.example](.env.example)). The web container starts only once the backend reports healthy.

### (a) One EC2 instance with docker compose and an IAM role (recommended for the demo)

The backend reads AWS through the instance's IAM role, so there are no keys to paste or leak.

**1. Role and instance.** Create the `OptiServeBackend` role and instance profile from [demo/aws_setup.md §1, Option A](demo/aws_setup.md#option-a-iam-role-recommended-when-the-backend-runs-on-ec2). Then launch Amazon Linux 2023 on a **t3.small**. A t3.micro's 1 GB is tight for building the web app.

```bash
AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query Parameter.Value --output text)
aws ec2 run-instances --image-id $AMI --instance-type t3.small --key-name <your-key> \
  --security-group-ids <sg-allowing-22-and-80-from-your-ip> \
  --iam-instance-profile Name=OptiServeBackend \
  --metadata-options HttpTokens=required,HttpPutResponseHopLimit=2 \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=optiserve-backend}]'
```

`HttpPutResponseHopLimit=2` matters: Docker adds one network hop, and with the default limit of 1 the container can't reach the instance metadata service, so the IAM role silently doesn't work. To fix an instance that's already running:
`aws ec2 modify-instance-metadata-options --instance-id <id> --http-tokens required --http-put-response-hop-limit 2`.

**2. Network.** Allow inbound port 80 from your own IP (the browser) and from the demo instances' security group (their agents). Agents in the same VPC should use this instance's **private** IP, for example `BACKEND_URL=http://10.0.1.23`. Then port 80 never has to be open to the whole internet.

**3. Docker on the instance** (SSH in as `ec2-user`):

```bash
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user && newgrp docker
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
docker buildx version >/dev/null 2>&1 || sudo curl -fsSL \
  "https://github.com/docker/buildx/releases/download/v0.19.3/buildx-v0.19.3.linux-$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')" \
  -o /usr/local/lib/docker/cli-plugins/docker-buildx
sudo chmod +x /usr/local/lib/docker/cli-plugins/*
docker compose version
```

**4. Configure and start:**

```bash
git clone --branch v2 https://github.com/Vishwas-shettyy/OptiServe.git && cd OptiServe
cp .env.example .env
sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env
docker compose build
docker compose run --rm -it --no-deps backend python scripts/hash_password.py   # paste the line into .env
nano .env    # ADMIN_EMAIL, ADMIN_PASSWORD_HASH, FRONTEND_ORIGIN=http://<public-ip>, LIVE_MODE=true for the demo
docker compose up -d
docker compose ps   # both services "healthy" after about 30 s
```

Open `http://<public-ip>`, sign in, then **Connect → AWS** with your region and **no keys**: the role is used. Agents report to `http://<private-ip>` from inside the VPC, or `http://<public-ip>` from elsewhere.

**Operate it:**

```bash
docker compose logs -f backend                   # jobs, AWS sync, errors (tokens and keys are never logged)
git pull && docker compose up -d --build         # update; the database stays on its volume
docker compose exec backend python -c "import sqlite3; sqlite3.connect('/data/optiserve.db').backup(sqlite3.connect('/data/backup.db'))" \
  && docker compose cp backend:/data/backup.db ./optiserve-backup.db      # backup
docker compose down                              # stop (add -v only if you also want to delete the data)
```

**HTTPS (optional):** put a Cloudflare Tunnel or an ALB with an ACM certificate in front of port 80, and set `FRONTEND_ORIGIN=https://…` so the login cookie becomes secure-only. nginx passes the tunnel's `X-Forwarded-Proto` through to the backend.

**Postgres (optional):** set `POSTGRES_PASSWORD` and `DATABASE_URL=postgresql+psycopg://optiserve:<password>@postgres:5432/optiserve` in `.env`, then run `docker compose --profile postgres up -d --build`. SQLite is enough for the demo and for a few dozen servers.

### (b) Local development, with a tunnel so cloud agents can reach your laptop

Agents on EC2 can't reach `localhost`. A tunnel gives your laptop a public HTTPS address. Agents only need `/api/ingest`, and they authenticate with their token.

```bash
# 1. Run OptiServe locally: either the containers…
cp .env.example .env    # set JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD_HASH, HTTP_PORT=8080, FRONTEND_ORIGIN=http://localhost:8080
docker compose up -d --build                 # → http://localhost:8080
# …or the dev servers (Quick start above): backend on :8000, Vite on :5173

# 2. Open a tunnel to the port that serves /api (8080 with Docker, 8000 with the dev servers)
cloudflared tunnel --url http://localhost:8080     # prints https://<random>.trycloudflare.com
# or
ngrok http 8080                                    # prints https://<random>.ngrok-free.app
```

3. Keep using OptiServe at `http://localhost:8080` (or `:5173`). On **Connect → Install the agent**, replace the address with the tunnel URL. The copied command then points agents at your laptop. For the ASG demo, use the tunnel URL as `BACKEND_URL` in the user-data.
4. AWS from a laptop: there's no IAM role, so use **Connect AWS** with the access keys from [aws_setup.md §1, Option B](demo/aws_setup.md#option-b-iam-user-with-access-keys-backend-on-your-laptop-or-elsewhere). They stay in memory only.

Good to know:
- Quick-tunnel URLs change every time the tunnel restarts. Point running agents at the new one with `sudo sed -i 's#^OPTISERVE_URL=.*#OPTISERVE_URL=https://<new>#' /etc/optiserve-agent.env && sudo systemctl restart optiserve-agent`. A named Cloudflare tunnel or a reserved ngrok domain keeps one stable address.
- If the laptop sleeps, agents keep up to 10 minutes of samples and send them when it's back. Anything older is dropped.
- ngrok's free-plan warning page only affects browsers, not the agent.
- Don't share the tunnel URL: anyone with it reaches your sign-in page.

## Demo script

The live demo runs on real AWS: an Auto Scaling group `optiserve-demo` and an idle `forgotten-test-box`. Full commands are in [demo/aws_setup.md](demo/aws_setup.md).

### Before (the day before, then 30 minutes before)

- [ ] Billing alarm set ([aws_setup.md §7](demo/aws_setup.md#7-billing-alarm-do-this-before-anything-else-is-left-running)) and its email confirmed.
- [ ] OptiServe deployed where the instances can reach it ([Deploy (a)](#a-one-ec2-instance-with-docker-compose-and-an-iam-role-recommended-for-the-demo)), with `LIVE_MODE=true`. Start with `DRY_RUN=true`.
- [ ] A demo-only agent token created: **Settings → Agent tokens** (name it `demo-asg`).
- [ ] AWS built: IAM access, security group, launch template with the user-data, optional ALB, ASG (min 1 / max 3 / desired 1, tagged `optiserve:managed=true`), and the lone `forgotten-test-box` (§1–6).
- [ ] The ASG instance answers: `curl http://<alb-or-ip>/metrics` returns `requests_per_min`.
- [ ] OptiServe → **Connect AWS** (`ap-south-1`): the instances and the group appear, and 14 days of history are brought in.
- [ ] **Home** shows breathing tiles; `forgotten-test-box` is asleep (zZ) after about 10 quiet minutes, with a "Stop it" suggestion.
- [ ] One rehearsal with dry run: run `python demo/loadgen.py --url http://<alb> --rps 30 --minutes 3`, approve the scale-up, see **Done** marked as a practice run in **Activity**.
- [ ] Switch dry run off: **Settings → Dry run** (confirm). Reload Home: the "Dry run" badge is gone.
- [ ] Laptop ready: `pip install httpx`, the loadgen command in a terminal, the AWS console open on the ASG's **Activity** tab.

### During (about 10 minutes)

1. **Connect (30 s):** show **Connect AWS**, or open Settings if it's already connected: account, region, instances and group found.
2. **Live fleet:** tiles breathe calmly; `forgotten-test-box` sleeps.
3. **Spike:** `python demo/loadgen.py --url http://<alb> --rps 30 --minutes 8`. The tile turns amber → red; the weather strip shows a storm.
4. **Copilot warns:** "CPU will reach …. Add 1 server now." → **Approve** → Approved → Changing… → Done. In the AWS console, desired capacity goes 1 → 2. The new instance's tile appears on its own within about 2 minutes, because its user-data installs the demo app and the agent.
5. **Waste:** "forgotten-test-box has been idle … Stop it" → **Approve** → the instance stops in AWS.
6. **Load ends** (loadgen ramps down by itself): after the 3-minute cooldown, OptiServe suggests going back to 1 server → **Approve** → desired 2 → 1.
7. **Proof:** **Activity** shows each change, who approved it, the result, the before/after chart, real ₹ saved and forecast accuracy.

If something stalls: **Servers → the group → Safety checks** says in plain words why OptiServe is holding back (cooldown, low data, health).

### Cleanup (same day)

- [ ] Run every command in [aws_setup.md §10](demo/aws_setup.md#10-cleanup-everything): ASG, launch template, lone instance, ALB and target group, security group, IAM user or role.
- [ ] Turn off the `demo-asg` token: **Settings → Agent tokens → Turn off**.
- [ ] Remove the AWS connection: **Settings → Connections → Remove**.
- [ ] Set `DRY_RUN=true` again (**Settings**) and `LIVE_MODE=false` for everyday use.
- [ ] In the EC2 console, check that no instances, load balancers or EBS volumes are left in the region. Keep the billing alarm.

## Roadmap

Next, once the v2 demo is solid:

- **Ask OptiServe:** a chat that answers "why?" questions from your own data ("Why did you add a server at 18:00?").
- **Alerts:** Slack and email for new suggestions, blocked actions and failed changes.
- **More clouds:** GCP managed instance groups and Azure VM scale sets, the same way as AWS.
- **Weekly plan report:** next week's capacity weather and expected cost, emailed every Monday.
- **Scheduled scaling suggestions** from the 7-day forecast (for example, "add a server every weekday at 09:00").
- **Teams:** more than one user, with roles (viewer / approver) and per-user approval history.
- **Per-region pricing** from the AWS Pricing API instead of the editable default table.

## Repository

| Folder | What's in it |
|---|---|
| `backend/` | FastAPI API, engine (forecast, plan, guardrails), AWS connector, executor, background jobs |
| `frontend/` | React app: Connect, Home, Servers, Server detail, Activity, Settings; nginx config for Docker |
| `agent/` | single-file metrics agent + one-line systemd installer |
| `demo/` | demo app, load generator, AWS setup guide, least-privilege IAM policy |
| `legacy/` | v1 (hackathon) app, kept for reference only, not run |

How we build it: [CLAUDE.md](CLAUDE.md). What we build: [OPTISERVE_V2_PLAN.md](OPTISERVE_V2_PLAN.md).
