# PROMPTS.md: build OptiServe in 10 prompts

## How to use this file (to save tokens)

1. Put `CODE.md` in the project root (the `optiserve/` folder). If you use Claude Code, also save a copy named `CLAUDE.md` there; Claude Code then reads it automatically every time.
2. Send the prompts **in order, one at a time**. Each one builds on the files the previous ones made.
3. After each prompt, check the "Done when" line yourself. Only move on once it passes.
4. **Start a fresh chat or `/clear` between prompts.** All the details live in CODE.md, so the AI doesn't need the old conversation. This saves the most tokens.
5. Use a Sonnet-class model for prompts 1 to 10 if your plan's usage is tight. Save the strongest model for fixing something that's stuck.
6. If a prompt fails, reply only: `Tests fail: <paste the error lines only>. Fix with minimal changes.` Don't paste whole files.

**Who runs which prompt:** A runs 1 to 6 (engine), B runs 7 and 8 (dashboard pages), and C runs 9 (Graveyard and Time Machine). D runs 10, then tests the 4 scenarios and works on the slides. B and C can start their pages with fake data while A works on 2 to 6. They then reconnect once `run_scenario` works.

---

## Prompt 1: project skeleton and config

```
Read CODE.md fully. Create the exact folder structure from section 2.
Write requirements.txt (streamlit, pandas, numpy, plotly, pytest).
Write engine/config.py fully (section 4, including risk_params and risk_label).
Create every other file listed with its imports, dataclasses (Scenario, ScenarioResult, ServiceResult) and the function signatures from sections 5–12, each body raising NotImplementedError for now.
Create tests/test_engine.py with one test that imports every engine module and checks risk_params(0), risk_params(1) match RISK_CHEAP/RISK_SAFE.
Run pytest. Reply in ≤10 lines.
```
Done when: `pip install -r requirements.txt` works and `python -m pytest -q` passes.

## Prompt 2: synthetic data generator

```
Follow CODE.md. Implement engine/data_gen.py fully (section 5): all 4 scenarios, exact patterns, events, sick-server leak and spike, zombies, current_servers, deterministic with SEED.
Add tests: each scenario has 672 hourly timestamps per server; columns match section 3; flash_sale events contain both sales; pay-07 max mem in last 24h > 90; zombie cpu < 5; two loads give identical data.
Run pytest and fix until green. Reply in ≤10 lines.
```
Done when: tests pass and `python -c "from engine.data_gen import load_scenario as l; print(l('flash_sale').metrics.head())"` prints rows.

## Prompt 3: profiler (server status and waste)

```
Follow CODE.md. Implement engine/profiler.py fully (section 6): profile_servers and waste_score with the exact status priority, idle_since, wasted_monthly and a readable reason.
Add tests from section 14 that only need the profiler: office_hours legacy servers are Zombie and most hr-portal servers are Wasteful; forgotten_servers has exactly 5 Zombies and waste_score > 25; sick_server pay-07 is Risky.
Run pytest and fix until green. Reply in ≤10 lines.
```
Done when: profiler tests pass.

## Prompt 4: forecaster

```
Follow CODE.md. Implement engine/forecaster.py fully (section 7): service_demand, detect_anomalies, forecast_service (event exclusion, anomaly cleaning, hour-of-week profile, std floor, trend ratio, z bands, event multipliers), naive_forecast, wape.
Use vectorised pandas, no Python loops over hours where avoidable.
Add tests: forecast has 168 rows and low <= expected <= high; flash_sale high at 2026-11-20 20:00 >= 4 × high at 2026-11-19 20:00; sick_server detects an anomaly at 2026-10-29 14:00.
Run pytest and fix until green. Reply in ≤10 lines.
```
Done when: forecaster tests pass.

## Prompt 5: planner and guardrails

```
Follow CODE.md. Implement engine/planner.py (section 8) and engine/guardrails.py (section 9) fully: needed_servers (CPU vs memory, whichever is larger), build_plan, recommend, apply_guardrails with all 6 rules in order, build_alerts.
Every rule returns status pass/adjusted/blocked with a clear one-line message.
Add tests: office_hours weekday hours 0–5 planned <= 3; flash_sale planned at 2026-11-20 18:00 > 10; sick_server health rule blocked and min planned >= 8; step limit never drops more than MAX_STEP_DOWN per hour; planned never below MIN_SERVERS.
Run pytest and fix until green. Reply in ≤10 lines.
```
Done when: planner and guardrail tests pass.

## Prompt 6: backtest, explainer and pipeline (engine complete)

```
Follow CODE.md. Implement engine/backtest.py (section 10), engine/explainer.py (section 11) and engine/pipeline.py (section 12) fully, including kpis, alerts and the __main__ summary printout.
Add every remaining acceptance test from section 14 (all rows), including determinism, risk 0 cost <= risk 1 cost, run time < 5 s per scenario, office_hours savings >= 30% with 0 plan shortfall, flash_sale plan shortfall < fixed shortfall, forecaster WAPE check, alerts content.
Run pytest and `python -m engine.pipeline`. Fix until everything is green. Reply in ≤10 lines with the key numbers per scenario.
```
Done when: all tests pass and `python -m engine.pipeline` prints sensible numbers for all 4 scenarios. **The backend is finished at this point; don't change engine contracts after this.**

## Prompt 7: app shell, styles and Overview page

```
Follow CODE.md sections 13 and 2. Implement ui/styles.py (dark theme CSS: cards, KPI tiles, status chips, alert boxes) and app.py (page config, CSS injection once, sidebar exactly as section 13, cached run_scenario wrapper, page router).
Implement ui/overview.py: scenario title + story, 4 KPI tiles (monthly cost, average utilisation, waste score, potential savings) in ₹ format, fleet status bar chart coloured by status, alerts list (critical first, coloured), and one recommendation card per service showing the explanation text.
Other pages: a simple "coming next" placeholder for now. No business logic in UI. Check that `python -c "import app"` has no import errors; run pytest. Reply in ≤10 lines.
```
Done when: `streamlit run app.py` opens, the scenario and risk slider change the Overview numbers.

## Prompt 8: Forecast & Plan page

```
Follow CODE.md. Implement ui/forecast_plan.py: service selector (services with plans only).
Chart 1 (Plotly): last 7 days actual requests line, forecast expected line, shaded low–high band, current capacity line (dashed, current × capacity_rps), planned capacity step line (planned × capacity_rps), event hours shaded with labels.
Chart 2: servers per hour, current vs planned (step lines).
Right column: recommendation card (action badge, current vs planned min–max, ₹ savings/month, %), explanation text, guardrail checklist (✅ pass, 🟡 adjusted, ⛔ blocked with message).
Wire it into app.py. Run pytest. Reply in ≤10 lines.
```
Done when: in Flash sale, the Friday spike, its band and pre-warmed capacity are visible; in Sick server, the health rule shows ⛔.

## Prompt 9: Server Graveyard and Time Machine

```
Follow CODE.md. Implement ui/graveyard.py: toggle "Graveyard view / Formal view".
Graveyard view: our own design — night-sky background, CSS grid of rounded tombstones (HTML via st.markdown unsafe_allow_html) for Zombie, Wasteful and Risky servers, sorted by wasted_monthly desc. Each stone: "R.I.P." (Zombie) / "On notice" (Wasteful) / "Do not bury" (Risky), name, instance_type, ₹/mo, idle since date, status chip in section 13 colours, hover tooltip with reason. Top banner: total ₹ wasted per month and count.
Formal view: readable table (renamed columns, ₹ formatting) of all servers with status, avg/p95 CPU, wasted ₹/mo, reason, recommended action; download as CSV button.
Implement ui/time_machine.py: per service, big comparison tiles (cost fixed vs OptiServe, savings %, shortfall hours fixed vs plan, over-provisioned hours), a Plotly chart of the test week (actual demand vs fixed capacity vs plan capacity, shortfall hours highlighted red), and a small "Forecast accuracy: OptiServe vs naive" WAPE comparison.
Wire both into app.py. Run pytest. Reply in ≤10 lines.
```
Done when: Forgotten servers shows 5 R.I.P. stones; Time Machine in Flash sale shows fixed setup shortfall vs none for OptiServe.

## Prompt 10: polish, verify, README

```
Follow CODE.md. Final pass, minimal changes only:
1. Run pytest and `python -m engine.pipeline`; fix any failure.
2. Check every row of section 14 again and every page with all 4 scenarios and risk 0 / 0.5 / 1; fix any error, empty chart, unformatted number or layout overflow.
3. Make sure switching scenario or risk never crashes and loads in < 3 s (cache).
4. Write README.md: one-paragraph pitch, how to run, project structure, how the engine works (6 bullet steps), the 4 scenarios, and a 3-minute demo script (Overview → Graveyard → Forecast & Plan → risk slider → Time Machine → Sick server).
Reply in ≤10 lines with what you fixed.
```
Done when: everything works for all 4 scenarios. Record the backup demo video now.
