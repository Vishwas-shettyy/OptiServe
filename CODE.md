# CODE.md — OptiServe build rules and spec

> Read this file fully before every task. It is the single source of truth.
> If a prompt and this file disagree, this file wins. Do not invent features outside it.

## 0. Rules for the AI coder (token-saving + quality)

1. Work only on the files named in the current prompt. Do not rewrite finished files unless the prompt says so.
2. Write complete, working code. No `TODO`, no `pass` placeholders, no pseudo-code, no "rest stays the same".
3. Dependencies allowed: `streamlit`, `pandas`, `numpy`, `plotly`, `pytest`. Nothing else.
4. Python 3.10+, type hints on every function, one-line docstring per function. No classes except the dataclasses named here.
5. Deterministic: every random call uses `np.random.default_rng(SEED)` (or a seed derived from it). Same input = same output.
6. Engine code (`engine/`) must never import `streamlit`. UI code (`app.py`, `ui/`) must never contain business logic: it only calls `engine.pipeline.run_scenario()` and draws results.
7. Keep the data contracts in section 3 exactly (column names, types, return shapes).
8. After coding, run `python -m pytest -q` and fix failures before finishing.
9. Final reply: max 10 lines — files changed, test result, anything blocked. Never paste whole files back.

## 1. Product in one line

OptiServe is a capacity-planning copilot: it forecasts server demand for the next 7 days, turns it into a right-sized hourly server plan, blocks risky scale-downs, explains every recommendation, and proves itself with a backtest. Data is synthetic, modelled on public cluster-trace patterns (daily + weekly cycles, noise, spikes).

## 2. Folder structure (create exactly this)

```
optiserve/
  app.py                 # Streamlit entry: sidebar + page router
  requirements.txt
  README.md
  engine/
    __init__.py
    config.py            # all constants (section 4)
    data_gen.py          # 4 synthetic scenarios (section 5)
    profiler.py          # server status + waste (section 6)
    forecaster.py        # demand forecast + anomalies + baseline (section 7)
    planner.py           # forecast -> servers per hour + recommendation (section 8)
    guardrails.py        # safety rules + alerts (section 9)
    backtest.py          # time machine (section 10)
    explainer.py         # plain-language reasons (section 11)
    pipeline.py          # run_scenario() glue + CLI smoke test (section 12)
  ui/
    __init__.py
    styles.py            # global CSS (dark theme, cards, tombstones)
    overview.py
    forecast_plan.py
    graveyard.py
    time_machine.py
  tests/
    test_engine.py
```

Run: `pip install -r requirements.txt` then `streamlit run app.py` from `optiserve/`.

## 3. Data contracts

**servers** (DataFrame, one row per server)
`server_id:str, name:str, service:str, instance_type:str, monthly_cost:float, capacity_rps:float`
(`capacity_rps` = requests per hour one server handles at 100% CPU; always 1000.0)

**metrics** (DataFrame, hourly, one row per server per hour, history only)
`timestamp:datetime64, server_id:str, service:str, requests:float, cpu_pct:float, mem_pct:float, error_rate:float`

**events** (DataFrame, known planned events)
`service:str, start:datetime64, end:datetime64 (inclusive hour), multiplier:float, label:str`

**Scenario** (dataclass in `data_gen.py`)
`key:str, title:str, story:str, servers:DataFrame, metrics:DataFrame, events:DataFrame, current_servers:dict[str,int]`
(`current_servers` = today's fixed server count per active service, excluding zombies)

**Service demand** (built by `forecaster.service_demand(metrics, servers)`), hourly per service:
`timestamp, service, requests (sum), mem_load_eq` where `mem_load_eq = sum(max(mem_pct - 30, 0)) / 70` across the service's servers (load-driven memory in server-equivalents).

**forecast** (DataFrame, 168 rows): `timestamp, expected, low, high, mem_high, is_event:bool`

**plan** (DataFrame, 168 rows): `timestamp, needed_raw:int, planned:int, current:int`

**ScenarioResult** (dataclass in `pipeline.py`)
`scenario, risk:float, profile:DataFrame, services:dict[str, ServiceResult], alerts:list[dict], kpis:dict`

**ServiceResult** (dataclass in `pipeline.py`)
`service, history:DataFrame (service demand), forecast, plan, guardrails:list[dict], recommendation:dict, explanation:str, backtest:dict, anomalies:list[dict]`

## 4. config.py constants

```
CURRENCY = "₹"
HOURS_PER_MONTH = 730
SEED = 42
START = "2026-10-19 00:00"      # Monday
HISTORY_DAYS = 28                # 2026-10-19 .. 2026-11-15 23:00
FORECAST_HOURS = 168             # 2026-11-16 00:00 .. 2026-11-22 23:00
TRAIN_DAYS = 21                  # backtest: train first 21 days, test last 7
CAPACITY_RPS = 1000.0
MIN_SERVERS = 2
MAX_STEP_DOWN = 2                # max servers removed per hour
PREWARM_HOURS = 2                # capacity ready this many hours before demand
MIN_HISTORY_DAYS = 7
LOW_CONFIDENCE_RATIO = 1.0       # mean((high-low)/expected) above this -> hold
ZOMBIE_CPU_P95 = 5.0
ZOMBIE_DAYS = 14
WASTEFUL_AVG_CPU = 25.0
HOT_CPU_P95 = 85.0
UNHEALTHY_MEM = 90.0
UNHEALTHY_ERROR = 0.05
OVERPROV_UTIL = 0.30
TARGET_CPU_FOR_WASTE = 65.0
RISK_CHEAP = {"target_util": 0.85, "z": 0.5}
RISK_SAFE  = {"target_util": 0.55, "z": 2.0}
DEFAULT_RISK = 0.5
```
`risk_params(risk: float) -> dict` linearly interpolates RISK_CHEAP (risk=0) to RISK_SAFE (risk=1); `risk_label(risk)` returns "Cheapest" (<0.34), "Balanced" (<0.67) or "Safest".

## 5. data_gen.py — 4 scenarios

`list_scenarios() -> list[tuple[key, title]]`, `load_scenario(key) -> Scenario`.
History = 672 hourly timestamps from START. Load of a service is split evenly across its non-zombie servers.
Per server per hour: `cpu_pct = clip(server_requests / capacity_rps * 100 * (1 + N(0,0.05)) + 2, 0, 100)`;
`mem_pct = clip(30 + 0.3*cpu_pct + N(0,2), 0, 100)`; `error_rate = 0.002 + |N(0,0.001)|`.
Zombie servers: requests uniform 0–5, cpu uniform 1–4, mem uniform 10–20.
Service demand noise: multiply by `(1 + N(0, 0.08))`, never below 0.

| key | title | services and servers | demand pattern | special |
|---|---|---|---|---|
| `office_hours` | Office-hours HR portal | `hr-portal` 12 servers, ₹7,000/mo; `legacy` 2 zombies (`old-staging-1`, `old-jenkins`) ₹5,000/mo | weekdays 09:00–18:59 = 6000 req/h (08:00 and 19:00 = 3000); other hours 300; weekends 400 | — |
| `flash_sale` | Festive flash sale | `shop-web` 10 servers, ₹8,000/mo; `legacy` 1 zombie (`demo-2024`) | `2500 + 2000*sin(pi*(hour-8)/16)` for hours 8–23 else 800; weekends ×1.2 | past sale 2026-11-12 18:00–23:00 ×6; future sale 2026-11-20 18:00–23:00 ×5; both in `events` |
| `forgotten_servers` | Forgotten servers | `analytics` 6 servers, ₹6,000/mo; `legacy` 5 zombies (`old-staging-1`, `old-staging-2`, `test-db-replica`, `demo-2024`, `old-jenkins`) ₹5,000/mo | `analytics`: 1500 + 2100*sin(pi*(hour-6)/14) for hours 6–20 else 900 | — |
| `sick_server` | Payments API with a sick server | `payments-api` 8 servers (`pay-01`..`pay-08`), ₹9,000/mo | 1200 + 2800*sin(pi*(hour-7)/15) for hours 7–22 else 1000 | `pay-07`: mem ramps 40→96 over last 72h, error_rate 0.08 in last 24h; one unexplained spike ×4 at 2026-10-29 14:00 (NOT an event) |

`current_servers` = count of non-zombie servers per service. Server ids: `<service-prefix>-NN` (e.g. `hr-01`), zombies use their names as ids.

## 6. profiler.py

`profile_servers(metrics, servers) -> DataFrame` with one row per server:
`server_id, name, service, instance_type, monthly_cost, avg_cpu, p95_cpu, max_mem_24h, err_24h, idle_since (timestamp or NaT), status, wasted_monthly, reason`
- Window: last 14 days (except health: last 24h).
- Status priority: **Risky** (max_mem_24h > UNHEALTHY_MEM or mean err_24h > UNHEALTHY_ERROR) > **Zombie** (p95_cpu < ZOMBIE_CPU_P95 over last ZOMBIE_DAYS) > **Hot** (p95_cpu > HOT_CPU_P95) > **Wasteful** (avg_cpu < WASTEFUL_AVG_CPU) > **Right-sized**.
- `idle_since` = start of the trailing run of days whose daily p95 cpu < ZOMBIE_CPU_P95 (Zombies only).
- `wasted_monthly`: Zombie = monthly_cost; Wasteful = monthly_cost * max(0, 1 - avg_cpu/TARGET_CPU_FOR_WASTE); others 0.
- `reason`: short human sentence, e.g. "CPU under 5% for 28 days".
`waste_score(profile) -> float` = sum(wasted_monthly) / sum(monthly_cost) * 100.

## 7. forecaster.py

- `service_demand(metrics, servers) -> DataFrame` (contract in section 3; zombies excluded).
- `detect_anomalies(series: Series, event_mask: Series) -> tuple[Series, list[dict]]`: per hour-of-week (weekday*24+hour) median and MAD; a non-event point is an anomaly if `x > median*1.5` and `|x-median| > 4*1.4826*MAD` (MAD>0). Replace with median. Each anomaly dict: `timestamp, value, expected`.
- `forecast_service(history, events, start, hours=168, z=1.25) -> tuple[forecast DataFrame, anomalies]`:
  1. Exclude event hours, clean anomalies.
  2. Profile = mean and std per hour-of-week over the last 3 weeks available (if < 2 weeks: std = 0.15*mean).
  3. std floor = 0.05*mean. Trend ratio = mean(last 7 days)/mean(previous 7 days) of the cleaned series with event hours excluded, clipped to [0.8, 1.3] (1.0 if < 14 days).
  4. expected = mean*ratio; low = max(0, expected - z*std); high = expected + z*std. Same for mem → `mem_high`.
  5. For forecast hours inside an event: multiply expected/low/high by the event multiplier, `is_event=True`.
- `naive_forecast(history, start, hours)`: value of the same hour one week earlier.
- `wape(actual, forecast) -> float` = sum|a-f| / sum(a).

## 8. planner.py

- `needed_servers(forecast, capacity_rps, target_util) -> Series[int]` = max( ceil(high / (capacity_rps*target_util)), ceil(mem_high / target_util) ), at least MIN_SERVERS.
- `build_plan(forecast, current, capacity_rps, target_util) -> plan DataFrame` (planned = needed_raw before guardrails).
- `recommend(plan, monthly_cost, current) -> dict` with: `current, planned_min, planned_avg, planned_max, current_monthly, planned_monthly, savings_monthly, savings_pct, action, peak_time, peak_servers, quiet_time`.
  planned_monthly = planned.mean() * monthly_cost. action: "scale_up" if planned_max > current and planned_avg >= 0.9*current; "scale_down" if planned_max <= current and planned_avg < 0.9*current; "schedule" if both up at peak and down on average; else "hold".

## 9. guardrails.py

`apply_guardrails(plan, forecast, profile_service, history_days, current) -> tuple[plan, list[dict]]`; each rule dict: `rule, status ("pass"|"adjusted"|"blocked"), message`. Apply in this order:
1. **Minimum servers**: planned >= MIN_SERVERS.
2. **Pre-warm**: planned[h] = max(planned[h .. h+PREWARM_HOURS]) — capacity ready before the peak.
3. **Step limit**: forward pass, planned[h] >= planned[h-1] - MAX_STEP_DOWN.
4. **Low data**: history_days < MIN_HISTORY_DAYS → planned = current, "blocked".
5. **Low confidence**: mean((high-low)/expected) > LOW_CONFIDENCE_RATIO → planned = max(planned, current), "blocked".
6. **Health**: any server in the service with status Risky → planned = max(planned, current), "blocked", message names the server.
`build_alerts(profile, services_results) -> list[dict]` each `severity ("critical"|"warning"|"info"), service, message`:
critical = Risky server; warning = forecast hour where high > current*capacity_rps*0.9 ("Capacity shortfall expected at Fri 20 Nov 20:00 — needs N servers, you run M"), only the first such hour per service; warning = each anomaly cluster; info = zombie count and their monthly cost. Sort critical → info.

## 10. backtest.py

`run_backtest(history, events, current, capacity_rps, monthly_cost, risk) -> dict`:
train = first TRAIN_DAYS days, test = last 7 days. Forecast the test week from train (events known), plan + guardrails (no health rule), compare with fixed `current`.
Return: `cost_fixed, cost_plan, savings_pct, shortfall_hours_fixed, shortfall_hours_plan, overprov_hours_fixed, overprov_hours_plan, wape_optiserve, wape_naive, series` where `series` = DataFrame `timestamp, actual, capacity_fixed, capacity_plan`.
shortfall hour = actual > servers*capacity_rps; overprov hour = actual/(servers*capacity_rps) < OVERPROV_UTIL; cost = server-hours * monthly_cost/HOURS_PER_MONTH.

## 11. explainer.py

`explain(service, rec, guardrails, risk) -> str`: 2–4 short sentences, plain language, numbers with thousand separators and CURRENCY. Template:
"`{service}`: run {min}–{max} servers instead of a fixed {current}. Busiest hour {peak_time:%a %d %b %H:%M} needs {peak_servers}. Saves ₹{savings:,}/month ({pct}%). Risk setting: {label}." + one sentence per blocked/adjusted rule.

## 12. pipeline.py

`run_scenario(key: str, risk: float = DEFAULT_RISK) -> ScenarioResult`: load scenario → profile → for each service that has non-zombie servers: demand, forecast, plan, guardrails, recommendation, explanation, backtest → alerts → kpis.
`kpis`: `monthly_cost` (all servers), `avg_util` (mean cpu of non-zombie servers, last 14 days), `waste_score`, `potential_savings` (zombie costs + positive service savings), `zombies`, `risky`.
`if __name__ == "__main__":` print one summary block per scenario (KPIs, recommendation, blocked rules, backtest numbers).

## 13. UI rules (Streamlit)

- `st.set_page_config(page_title="OptiServe", layout="wide")`. Dark theme via `ui/styles.py` CSS injected once.
- Sidebar: logo text "OptiServe", subtitle "Capacity-planning copilot"; scenario selectbox (titles); risk slider 0.0–1.0 step 0.05 with live label (Cheapest/Balanced/Safest); page radio: Overview, Forecast & Plan, Server Graveyard, Time Machine; footer note "Synthetic data modelled on public cluster-trace patterns".
- Cache: `@st.cache_data` on a wrapper around `run_scenario(key, risk)`.
- Charts: Plotly only, `template="plotly_dark"`, transparent background.
- Colours: Right-sized `#22c55e`, Wasteful `#f59e0b`, Zombie `#a78bfa`, Hot `#fb923c`, Risky `#ef4444`, accent `#38bdf8`.
- Money always as `₹12,345`. Never show raw DataFrames without renamed, readable columns.
- Graveyard is our own design (not copied): night background, rounded tombstones, chips by status.

## 14. Expected behaviour (acceptance tests — must all pass)

| scenario | assertion |
|---|---|
| all | `run_scenario` runs in < 5 s; same output on two runs (determinism) |
| all | plan cost at risk 0.0 <= plan cost at risk 1.0 |
| office_hours | `hr-portal` planned servers at hours 00:00–05:00 on forecast weekdays <= 3; backtest savings_pct >= 30; shortfall_hours_plan == 0; both `legacy` servers Zombie; most `hr-portal` servers Wasteful |
| flash_sale | forecast high at 2026-11-20 20:00 >= 4 × high at 2026-11-19 20:00; planned at 2026-11-20 18:00 > 10; a "Capacity shortfall expected" warning exists; backtest shortfall_hours_plan < shortfall_hours_fixed |
| forgotten_servers | exactly 5 Zombies; waste_score > 25 |
| sick_server | `pay-07` Risky; health rule "blocked"; min planned >= 8; a critical alert names `pay-07`; >= 1 anomaly detected around 2026-10-29 14:00 |
| forecaster | office_hours backtest `wape_optiserve <= wape_naive * 1.05` |
