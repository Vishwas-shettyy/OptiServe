# OptiServe

**Connect your servers in 2 minutes. OptiServe watches real usage, warns you before you run short, finds servers you're wasting money on, and fixes it with one click, only when you approve.**

- Real data only: the OptiServe agent on any Linux server, or a read-only AWS connection (EC2, Auto Scaling, CloudWatch).
- Copilot, not autopilot: every change waits for a person to click **Approve**, passes nine safety checks, and is logged.
- Savings are counted only from real actions: servers removed × hours × price.

How we build it: [CLAUDE.md](CLAUDE.md). What we build: [OPTISERVE_V2_PLAN.md](OPTISERVE_V2_PLAN.md).

## Quick start (local)

```bash
# Backend (Python 3.11+)
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # set JWT_SECRET, ADMIN_EMAIL
.venv/bin/python scripts/hash_password.py   # paste the hash into ADMIN_PASSWORD_HASH
.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend (Node 20+), in another terminal
cd frontend && npm install && npm run dev   # http://localhost:5173, /api is proxied to :8000
```

Sign in, then follow **Connect** to install the agent or connect AWS.

**Tests:** `cd backend && .venv/bin/python -m pytest -q` · `cd frontend && npm run build && npm test` · demo kit: `backend/.venv/bin/python -m pytest -q demo/tests`

## Repository

| Folder | What's in it |
|---|---|
| `backend/` | FastAPI API, engine (forecast, plan, guardrails), AWS connector, background jobs |
| `frontend/` | React app: Connect, Home, Servers, Server detail, Activity, Settings |
| `agent/` | single-file metrics agent + one-line systemd installer |
| `demo/` | demo app, load generator, AWS setup guide, least-privilege IAM policy |
| `legacy/` | v1 (hackathon) app, kept for reference only |

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

## Demo checklist

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
