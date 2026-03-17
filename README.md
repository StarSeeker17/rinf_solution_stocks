# Inventory Transfer Optimization (MVP) — Project Presentation

## 1) What problem this solves

You have **multiple stores** carrying the **same catalog**. Some stock sits in the “wrong” store (slow sales / excess cover), while other stores would sell it faster. The goal is to recommend **store-to-store transfers** that:

- **increase expected profit** (sell margin in a better location),
- **account for logistics cost** (fixed + per-unit transport),
- **avoid creating shortages** (don’t transfer below safety stock).

This repository is an **MVP**: it demonstrates an end-to-end pipeline and a usable Streamlit UI with synthetic but realistic data.

## 2) What the app does (in one sentence)

Given sales+stock history, product margins, and inter-store transfer costs, the app **forecasts demand**, flags **stale/excess inventory**, generates all possible **source→destination** transfer candidates, computes **net profit**, and selects **non-conflicting profitable routes**.

## 3) What’s in the repo (main files)

- **`app.py`**: Streamlit UI. Loads data, runs the pipeline, renders tables/charts, and exposes sliders that directly change the recommendations.
- **`forecast.py`**: Forecasting + “signals” layer:
  - builds a complete daily panel per (store, product),
  - forecasts next \(N\) days demand,
  - computes last-sale metrics,
  - flags stale/excess inventory.
- **`cost_computation.py`**: Profit and transfer optimization layer:
  - computes safety stock and target stock,
  - generates transfer candidates and profit per route,
  - picks best **non-conflicting** transfers (greedy).
- **`generate_data.py`**: Synthetic dataset generator:
  - writes `product_master.csv`, `transfer_costs.csv`, `sales_inventory.csv`.
- **`requirements.txt`**: minimal dependencies to run Streamlit + computation.

## 4) Data model (inputs)

### Sales + inventory (`sales_inventory.csv`)
Expected columns (validated in `forecast.prepare_daily_data`):

- `date` (YYYY-MM-DD)
- `store_id`
- `product_id`
- `units_sold`
- `stock_on_hand`

Note: the generator logs rows only for **days with sales**, plus the **last day** to capture final stock. The pipeline expands this into a complete daily panel.

### Product master (`product_master.csv`)
Expected columns:

- `product_id`
- `unit_cost`
- `unit_sale_price`

### Transfer costs (`transfer_costs.csv`)
Expected columns:

- `from_store`
- `to_store`
- `transport_cost_fixed`
- `transport_cost_per_unit`

## 5) Streamlit UI (what you see)

The UI (`app.py`) is a “glass box”: it shows intermediate results (summary, signals, audits) and final recommendations.

### Controls (and how they change results)

- **Forecast start date**: shifts the forecast window and last-sale calculations.
- **Safety stock days**: increases reserved stock at sources (above the minimum floor), reducing what can be transferred.
- **Target cover days**: increases target stock at destinations, increasing needed units and possible transfers.
- **Stale stock threshold**: affects stale flags and, when enabled, the source filter.
- **Only allow stale sources**: restricts sources to stores/products that are stale or low-selling.

## 6) What makes this an MVP (current limitations)

- **No persistence / state updates**: executing a transfer doesn’t update stock permanently (CSV is read-only input).
- **Forecasting is intentionally simple**: no model training, no cross-validation, no uncertainty intervals.
- **Optimization is greedy**: works well as a heuristic but doesn’t guarantee global optimum.
- **File upload flow is simplified**: currently one uploaded CSV is reused for multiple datasets; in production you’d separate uploads or enforce a schema/bundle.
- **Sentinel values for “never sold”**: `999` is used for computation; UI should humanize this for readability (the repo already has `humanize_days_since_last_sale`).

## 7) Roadmap: MVP → real application (practical, incremental)

### Phase 1 — Make it reliable (still small)
- **Input validation**: strict schema checks + helpful error messages for uploaded data.
- **Configuration**: centralize constants (stale thresholds, low-qty threshold, min safety stock, max cover used in charts).
- **Test harness**: a few unit tests for safety-stock constraint, candidate generation, and “no stock cannot be stale”.

### Phase 2 — Add state and workflows (first “real app” step)
- **SQLite persistence** (or Postgres later):
  - tables: stores, products, daily_sales, inventory_snapshots, transfer_costs, transfers
- **Execute transfers**:
  - allow “approve transfer” in UI,
  - record a transfer event,
  - update inventory (and re-run pipeline on updated state).

### Phase 3 — Decision quality + trust
- **Forecast backtesting** (accuracy report per store/product; detect bias and stockout distortion).
- **Uncertainty-aware decisions**:
  - demand intervals,
  - conservative safety stock when uncertainty is high.
- **Explainability**:
  - “why this transfer” with a clear bridge: margin, cost, source risk, expected net.

### Phase 4 — Scaling and integration
- **Real ETL** from ERP/POS systems.
- **Role-based access** and audit logs.
- **Performance**: cache intermediate results; consider vectorized candidate computation and/or an LP/MIP solver for optimization when scale grows.

## 8) How to run (quick)

```bash
pip install -r requirements.txt
streamlit run app.py
```

To generate fresh synthetic data:

```bash
python generate_data.py
```

