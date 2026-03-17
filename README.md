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

## 5) How it works (end-to-end pipeline)

### Step A — Build a clean daily time series (`forecast.py`)

1) **`prepare_daily_data(df)`**
- Creates a **complete daily grid** of all dates × all stores × all products.
- Missing `units_sold` becomes 0.
- `stock_on_hand` is forward-filled within each (store, product).

2) **`add_features(df)`**
- Adds day-of-week (`dow`) and a stockout flag (`is_stockout`).
- Uses `effective_sales = NaN` on stockout days so stockouts don’t artificially lower demand estimates.

### Step B — Forecast demand (`forecast.py`)

3) **Weighted moving average + weekday factor**
- **`compute_base_forecast`**: weighted moving average over last 28 days of `effective_sales` (more recent days weigh more).
- **`compute_weekday_factor`**: relative weekday multiplier, clamped to \([0.7, 1.3]\).

4) **`forecast_next_n_days(df, start_date, horizon=7)`**
- Forecasts each day independently for each (store, product).
- Produces:
  - `daily_forecasts`: per-day forecast detail,
  - `summary`: per (store, product) `forecast_7d`, `avg_daily_forecast`, `current_stock`, `days_of_cover`.

### Step C — Identify stale/excess inventory (`forecast.py`)

5) **`add_last_sale_info(df, as_of_date)`**
- Computes `last_sale_date`, `days_since_last_sale` (uses **999** if never sold), and `sold_last_30d`.

6) **`build_transfer_signal(...)`**
- Flags inventory using last-sale + cover metrics:
  - `stale_stock_flag`: **only if `current_stock > 0`** AND `days_since_last_sale >= threshold`
  - `low_quantity_flag`: `sold_last_30d < 5` (low selling, not low stock)
  - `excess_stock_flag`: **only if `current_stock > 0`** AND (`days_of_cover > 14` OR stale OR low-selling)

This is intentionally “screening logic” and not an optimizer.

### Step D — Compute profitable transfers (`cost_computation.py`)

7) **`prepare_profit_inputs(summary, product_master, safety_days, target_cover_days)`**
- Adds:
  - `unit_margin = unit_sale_price - unit_cost`
  - `safety_stock = max(avg_daily_forecast * safety_days, MIN_SAFETY_STOCK)`
  - `target_stock = avg_daily_forecast * target_cover_days`
  - `transferable_units = max(0, floor(current_stock - safety_stock))`
  - `needed_units = max(0, ceil(target_stock - current_stock))`

Important: safety stock is a **transfer constraint** (don’t transfer below it). It is not a “hard operational minimum” that blocks sales.

8) **`generate_transfer_candidates(...)`**
- Defines:
  - **sources**: rows with `transferable_units > 0` (optionally restricted by last-sale filters if `require_stale_source=True`)
  - **destinations**: rows with `needed_units > 0`
- Creates all same-product source→destination pairs and joins transfer costs.
- For each candidate:
  - `proposed_qty = min(source_excess, dest_need)`
  - `destination_gain = proposed_qty * unit_margin`
  - `source_loss` models “lost sales at source” using a simple risk ratio:
    - `min(1, source_forecast_7d / source_stock)`
  - `transport_cost = fixed + proposed_qty * per_unit`
  - `net_profit = destination_gain - source_loss - transport_cost`
- Keeps only `net_profit > 0`.

9) **`choose_best_non_conflicting_transfers(candidates)`**
- Greedy selection in descending net profit.
- Prevents double-counting inventory by tracking remaining source capacity and destination need.

## 6) Streamlit UI (what you see)

The UI (`app.py`) is a “glass box”: it shows intermediate results (summary, signals, audits) and final recommendations.

### Controls (and how they change results)

- **Forecast start date**: shifts the forecast window and last-sale calculations.
- **Safety stock days**: increases reserved stock at sources (above the minimum floor), reducing what can be transferred.
- **Target cover days**: increases target stock at destinations, increasing needed units and possible transfers.
- **Stale stock threshold**: affects stale flags and, when enabled, the source filter.
- **Only allow stale sources**: restricts sources to stores/products that are stale or low-selling.

## 7) What makes this an MVP (current limitations)

- **No persistence / state updates**: executing a transfer doesn’t update stock permanently (CSV is read-only input).
- **Forecasting is intentionally simple**: no model training, no cross-validation, no uncertainty intervals.
- **Optimization is greedy**: works well as a heuristic but doesn’t guarantee global optimum.
- **File upload flow is simplified**: currently one uploaded CSV is reused for multiple datasets; in production you’d separate uploads or enforce a schema/bundle.
- **Sentinel values for “never sold”**: `999` is used for computation; UI should humanize this for readability (the repo already has `humanize_days_since_last_sale`).

## 8) Roadmap: MVP → real application (practical, incremental)

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

## 9) How to run (quick)

```bash
pip install -r requirements.txt
streamlit run app.py
```

To generate fresh synthetic data:

```bash
python generate_data.py
```

