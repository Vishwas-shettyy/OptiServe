# OptiServe

**OptiServe is a capacity-planning copilot.** Most teams run a fixed number of servers around the clock, so they pay for idle machines at 3 a.m. and still run short at a festive-sale peak. OptiServe forecasts each service's demand for the next 7 days and turns it into a right-sized, hour-by-hour server plan. Safety guardrails block risky scale-downs, such as removing servers while one is failing. Every recommendation comes with a plain-language reason. The Time Machine backtest replays last week to show what the plan would have saved without running short. All costs are in ₹. The data is synthetic, modelled on public cluster-trace patterns: daily and weekly cycles, noise and spikes.

## How to run

```bash
cd optiserve
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py              # dashboard at http://localhost:8501
python -m engine.pipeline         # text summary of all 4 scenarios
python -m pytest -q               # engine and acceptance tests
```

Requires Python 3.10+. Dependencies: streamlit, pandas, numpy, plotly, pytest.

## Project structure

```
optiserve/
  app.py               # Streamlit entry: page config, sidebar, cached run_scenario, page router
  requirements.txt
  engine/              # pure Python, never imports streamlit
    config.py          # all constants and risk settings
    data_gen.py        # the 4 synthetic scenarios
    profiler.py        # per-server status (Zombie, Wasteful, Hot, Risky, Right-sized) and waste
    forecaster.py      # hour-of-week demand forecast, anomaly detection, naive baseline, WAPE
    planner.py         # forecast → servers per hour → recommendation
    guardrails.py      # safety rules and alerts
    backtest.py        # Time Machine: train 21 days, test the last 7
    explainer.py       # plain-language reasons
    pipeline.py        # run_scenario() glue and CLI summary
  ui/
    styles.py          # dark-theme CSS: cards, KPI tiles, chips, tombstones
    overview.py        # KPIs, fleet status, alerts, recommendations
    forecast_plan.py   # demand forecast, capacity plan, guardrail checklist
    graveyard.py       # tombstone view and formal table with CSV export
    time_machine.py    # backtest: fixed fleet vs OptiServe
  tests/test_engine.py
```

## How the engine works

1. **Profile:** classify every server from 14 days of CPU, memory and errors as Risky, Zombie, Hot, Wasteful or Right-sized, and price its waste in ₹/month.
2. **Clean:** add up demand per service, set known events (such as sales) aside, and replace unexplained spikes with the normal value for that hour.
3. **Forecast:** build an hour-of-week profile from the last 3 weeks and adjust it for recent trend. The forecast is an expected value with a low–high band; the risk slider sets the band's width. Known future events are then multiplied in.
4. **Plan:** convert the band's high end into servers per hour at a target utilisation that also depends on the risk slider.
5. **Guardrails:** enforce minimum servers, pre-warm capacity 2 hours before peaks, limit how many servers are removed per hour, and block scale-downs when data is thin, the forecast is uncertain or a server is unhealthy.
6. **Explain and prove it:** write a plain-language reason with the ₹ savings, raise alerts, and backtest on the last week against a fixed fleet and a naive "same hour last week" forecast.

## The 4 scenarios

| Scenario | What happens | What OptiServe shows |
|---|---|---|
| **Office-hours HR portal** | 12 servers run 24/7 for traffic that only comes on weekdays from 9 to 6; 2 forgotten legacy servers | Scale to about 2 servers at night, saving about 55%; both legacy servers are Zombies |
| **Festive flash sale** | 10 servers face a sale on Fri 20 Nov from 18:00 to 23:00, at 5× normal traffic | A "Capacity shortfall expected" warning and a pre-warmed scale-up to 36 servers |
| **Forgotten servers** | A small analytics fleet plus 5 abandoned servers | 5 tombstones in the Graveyard and a waste score above 40% |
| **Payments API with a sick server** | `pay-07` memory climbs to 96% with errors at 8%; one unexplained spike | The Health guardrail blocks every scale-down, a critical alert names `pay-07`, and the anomaly is flagged |

## 3-minute demo script

1. **Overview (0:00–0:40).** Choose *Office-hours HR portal*. Walk through the 4 KPI tiles: monthly cost, utilisation of about 20%, waste score of about 72%, and potential savings. Point to the fleet status chart, which is mostly amber (Wasteful), then read the hr-portal recommendation card aloud.
2. **Server Graveyard (0:40–1:10).** Switch to *Forgotten servers*. Show the banner with the ₹ wasted per month, then hover a "R.I.P." stone to see the reason (for example "CPU under 5% for 28 days"). Toggle to *Formal view* and click *Download as CSV*: this is the version for finance.
3. **Forecast & Plan (1:10–1:50).** Switch to *Festive flash sale*. Show the forecast band rising into the shaded sale window, the dashed current capacity line falling short of it, and the green planned step line rising early because of pre-warming. Point out the guardrail checklist on the right.
4. **Risk slider (1:50–2:15).** Move the slider from *Cheapest* (0.0) to *Safest* (1.0). The band widens, the planned line rises and the savings fall. The trade-off is explicit and stays under your control.
5. **Time Machine (2:15–2:40).** On the flash sale, compare 6 shortfall hours for the fixed fleet with 0 for OptiServe, at about 17% lower cost. On the right, OptiServe's forecast error (WAPE) is about 8%, against about 27% for the naive forecast.
6. **Sick server (2:40–3:00).** Switch to *Payments API with a sick server*. The Overview shows a critical alert for `pay-07`. Forecast & Plan shows ⛔ Health blocked: OptiServe keeps all 8 servers rather than save money while a server is failing.
