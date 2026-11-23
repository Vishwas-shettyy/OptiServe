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

## Demo checklist

The live demo runs on real AWS: an Auto Scaling group `optiserve-demo` and an idle `forgotten-test-box`. Full commands are in [demo/aws_setup.md](demo/aws_setup.md).

### Before (the day before, then 30 minutes before)

- [ ] Billing alarm set ([aws_setup.md §7](demo/aws_setup.md#7-billing-alarm-do-this-before-anything-else-is-left-running)) and its email confirmed.
- [ ] Backend deployed where the instances can reach it, with `LIVE_MODE=true`. Start with `DRY_RUN=true`.
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
