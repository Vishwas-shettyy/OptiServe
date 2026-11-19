# OptiServe

Capacity-planning copilot: forecasts server demand for the next 7 days, turns it into a right-sized hourly server plan, blocks risky scale-downs, explains every recommendation, and proves itself with a backtest. Data is synthetic, modelled on public cluster-trace patterns.

## Run

```
pip install -r requirements.txt
streamlit run app.py
```

Tests: `python -m pytest -q`
