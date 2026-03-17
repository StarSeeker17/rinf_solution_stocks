import pandas as pd
import numpy as np

MIN_SAFETY_STOCK = 10.0

def compute_safety_stock(
    avg_daily_forecast: pd.Series,
    safety_days: float = 3.0,
    min_floor: float = MIN_SAFETY_STOCK,
) -> pd.Series:
    """
    Compute safety stock as (avg_daily_forecast * safety_days), with a hard minimum floor.

    Safety stock is a planning buffer:
    - Transfers are not allowed to reduce stock below this level.
    - Customer sales can still reduce stock below this level over time.
    """

    computed_safety = avg_daily_forecast * safety_days
    return np.maximum(computed_safety, min_floor)




def prepare_profit_inputs(
    forecast_summary: pd.DataFrame,
    product_master: pd.DataFrame,
    safety_days: float = 3.0,
    target_cover_days: float = 7.0
) -> pd.DataFrame:
    """
    Add margin, safety stock, excess stock, and shortage estimates to forecast summary.
    """
    df = forecast_summary.merge(product_master, on="product_id", how="left").copy()

    # Required columns in product_master:
    # product_id, unit_sale_price, unit_cost
    df["unit_margin"] = df["unit_sale_price"] - df["unit_cost"]

    df["safety_stock"] = compute_safety_stock(df["avg_daily_forecast"], safety_days=safety_days)

    # How much stock we would like to have over the horizon / cover window
    df["target_stock"] = df["avg_daily_forecast"] * target_cover_days

    # Stock above safety zone = potentially transferable
    df["transferable_units"] = np.maximum(0, np.floor(df["current_stock"] - df["safety_stock"])).astype(int)

    # Stock needed to reach target cover
    df["needed_units"] = np.maximum(0, np.ceil(df["target_stock"] - df["current_stock"])).astype(int)

    return df


def generate_transfer_candidates(
    profit_inputs: pd.DataFrame,
    transfer_costs: pd.DataFrame,
    days_since_last_sale_df: pd.DataFrame = None,
    stale_days_threshold: int = 30, # Base this off the UI slider, or default to 30
    require_stale_source: bool = False,
    low_qty_threshold: int = 5
) -> pd.DataFrame:
    """
    Build all source-destination-product candidate transfers and compute net profit.

    transfer_costs must have:
    from_store, to_store, transport_cost_fixed, transport_cost_per_unit
    """
    df = profit_inputs.copy()

    if days_since_last_sale_df is not None:
        df = df.merge(
            days_since_last_sale_df[["store_id", "product_id", "days_since_last_sale", "sold_last_30d"]],
            on=["store_id", "product_id"],
            how="left"
        )
    else:
        df["days_since_last_sale"] = np.nan
        df["sold_last_30d"] = np.nan

    # source candidates
    sources = df[df["transferable_units"] > 0].copy()
    if require_stale_source:
        # ALLOW: Sources that haven't sold OR sold low quantities
        sources = sources[
            (sources["days_since_last_sale"] >= stale_days_threshold) |
            (sources["sold_last_30d"] <= low_qty_threshold)
        ].copy()

    # destination candidates
    destinations = df[df["needed_units"] > 0].copy()

    if sources.empty or destinations.empty:
        return pd.DataFrame(columns=[
            "product_id", "source_store", "dest_store", "proposed_qty",
            "unit_margin", "source_stock", "dest_stock", "source_forecast_7d",
            "dest_forecast_7d", "source_days_of_cover", "dest_days_of_cover",
            "source_days_since_last_sale", "transport_cost_fixed", "transport_cost_per_unit",
            "destination_gain", "source_loss", "transport_cost", "net_profit",
            "profit_per_unit_transferred"
        ])

    # rename columns for join
    src = sources.rename(columns={
        "store_id": "source_store",
        "current_stock": "source_stock",
        "avg_daily_forecast": "source_avg_daily_forecast",
        "forecast_7d": "source_forecast_7d",
        "days_of_cover": "source_days_of_cover",
        "transferable_units": "max_transferable_units",
        "days_since_last_sale": "source_days_since_last_sale"
    })

    dst = destinations.rename(columns={
        "store_id": "dest_store",
        "current_stock": "dest_stock",
        "avg_daily_forecast": "dest_avg_daily_forecast",
        "forecast_7d": "dest_forecast_7d",
        "days_of_cover": "dest_days_of_cover",
        "needed_units": "max_needed_units"
    })

    # match only same product, different stores
    candidates = src.merge(
        dst,
        on=["product_id", "unit_sale_price", "unit_cost", "unit_margin"],
        how="inner",
        suffixes=("_src", "_dst")
    )

    candidates = candidates[candidates["source_store"] != candidates["dest_store"]].copy()

    # attach transport cost
    candidates = candidates.merge(
        transfer_costs,
        left_on=["source_store", "dest_store"],
        right_on=["from_store", "to_store"],
        how="left"
    )

    # If no explicit cost row, assume impossible / too expensive
    candidates["transport_cost_fixed"] = candidates["transport_cost_fixed"].fillna(np.inf)
    candidates["transport_cost_per_unit"] = candidates["transport_cost_per_unit"].fillna(np.inf)

    # Proposed quantity = min(excess at source, need at destination)
    candidates["proposed_qty"] = np.minimum(
        candidates["max_transferable_units"],
        candidates["max_needed_units"]
    ).astype(int)

    candidates = candidates[candidates["proposed_qty"] > 0].copy()

    # Destination gain:
    # destination can likely monetize units up to its shortage
    candidates["destination_gain"] = candidates["proposed_qty"] * candidates["unit_margin"]

    # Source loss:
    # approximate how many of those units source might still sell over next 7 days
    # but cap by quantity being transferred
    source_sell_risk_ratio = np.where(
        candidates["source_stock"] > 0,
        np.minimum(1.0, candidates["source_forecast_7d"] / candidates["source_stock"]),
        0.0
    )
    candidates["source_loss"] = (
        candidates["proposed_qty"] * source_sell_risk_ratio * candidates["unit_margin"]
    )

    # Transport costs
    candidates["transport_cost"] = (
        candidates["transport_cost_fixed"] +
        candidates["proposed_qty"] * candidates["transport_cost_per_unit"]
    )

    # Net profit
    candidates["net_profit"] = (
        candidates["destination_gain"]
        - candidates["source_loss"]
        - candidates["transport_cost"]
    )

    # ROI-like metric
    candidates["profit_per_unit_transferred"] = np.where(
        candidates["proposed_qty"] > 0,
        candidates["net_profit"] / candidates["proposed_qty"],
        0.0
    )

    # Keep only profitable candidates
    candidates = candidates[candidates["net_profit"] > 0].copy()

    # Useful ordering
    candidates = candidates.sort_values(
        ["net_profit", "profit_per_unit_transferred", "source_days_since_last_sale"],
        ascending=[False, False, False]
    )

    cols = [
        "product_id",
        "source_store",
        "dest_store",
        "proposed_qty",
        "unit_margin",
        "source_stock",
        "dest_stock",
        "source_forecast_7d",
        "dest_forecast_7d",
        "source_days_of_cover",
        "dest_days_of_cover",
        "source_days_since_last_sale",
        "transport_cost_fixed",
        "transport_cost_per_unit",
        "destination_gain",
        "source_loss",
        "transport_cost",
        "net_profit",
        "profit_per_unit_transferred"
    ]

    return candidates[cols]


def choose_best_non_conflicting_transfers(candidates: pd.DataFrame) -> pd.DataFrame:
    """
    Greedy selector:
    choose profitable transfers in descending net profit order,
    while respecting remaining source stock and destination need.

    Good first production heuristic.
    """
    if candidates.empty:
        return candidates.copy()

    work = candidates.copy()

    # Remaining capacities
    source_remaining = (
        work.groupby(["source_store", "product_id"])["proposed_qty"]
        .max()
        .to_dict()
    )
    dest_remaining = (
        work.groupby(["dest_store", "product_id"])["proposed_qty"]
        .max()
        .to_dict()
    )

    selected_rows = []

    for _, row in work.sort_values("net_profit", ascending=False).iterrows():
        src_key = (row["source_store"], row["product_id"])
        dst_key = (row["dest_store"], row["product_id"])

        qty = min(
            row["proposed_qty"],
            source_remaining.get(src_key, 0),
            dest_remaining.get(dst_key, 0)
        )

        if qty <= 0:
            continue

        selected = row.copy()
        selected["selected_qty"] = qty

        # recompute quantity-sensitive fields
        selected["destination_gain"] = qty * row["unit_margin"]

        source_sell_risk_ratio = 0.0
        if row["source_stock"] > 0:
            source_sell_risk_ratio = min(1.0, row["source_forecast_7d"] / row["source_stock"])

        selected["source_loss"] = qty * source_sell_risk_ratio * row["unit_margin"]
        selected["transport_cost"] = row["transport_cost"]  # fixed already bundled at candidate level
        selected["net_profit"] = (
            selected["destination_gain"]
            - selected["source_loss"]
            - selected["transport_cost"]
        )

        if selected["net_profit"] > 0:
            selected_rows.append(selected)
            source_remaining[src_key] -= qty
            dest_remaining[dst_key] -= qty

    if not selected_rows:
        return pd.DataFrame()

    return pd.DataFrame(selected_rows).sort_values("net_profit", ascending=False)
def build_source_audit_table(
    profit_inputs: pd.DataFrame,
    days_since_last_sale_df: pd.DataFrame = None
) -> pd.DataFrame:
    df = profit_inputs.copy()

    if days_since_last_sale_df is not None:
        df = df.merge(
            days_since_last_sale_df[["store_id", "product_id", "days_since_last_sale"]],
            on=["store_id", "product_id"],
            how="left"
        )

    out = df.rename(columns={
        "store_id": "source_store",
        "current_stock": "source_stock",
        "avg_daily_forecast": "source_avg_daily_forecast",
        "forecast_7d": "source_forecast_7d",
        "days_of_cover": "source_days_of_cover",
        "transferable_units": "max_transferable_units",
        "days_since_last_sale": "source_days_since_last_sale"
    })

    # Only show stores/products that can actually send stock
    out = out[out["max_transferable_units"] > 0].copy()

    cols = [
        "product_id",
        "source_store",
        "source_stock",
        "source_avg_daily_forecast",
        "source_forecast_7d",
        "source_days_of_cover",
        "source_days_since_last_sale",
        "safety_stock",
        "max_transferable_units",
        "unit_margin"
    ]

    return out[cols].sort_values(
        ["product_id", "source_store"]
    )


def build_destination_audit_table(profit_inputs: pd.DataFrame) -> pd.DataFrame:
    out = profit_inputs.copy().rename(columns={
        "store_id": "dest_store",
        "current_stock": "dest_stock",
        "avg_daily_forecast": "dest_avg_daily_forecast",
        "forecast_7d": "dest_forecast_7d",
        "days_of_cover": "dest_days_of_cover",
        "needed_units": "max_needed_units"
    })

    # Only show stores/products that actually need stock (true destinations)
    out = out[out["max_needed_units"] > 0].copy()

    cols = [
        "product_id",
        "dest_store",
        "dest_stock",
        "dest_avg_daily_forecast",
        "dest_forecast_7d",
        "dest_days_of_cover",
        "target_stock",
        "max_needed_units",
        "unit_margin"
    ]

    return out[cols].sort_values(
        ["product_id", "dest_store"]
    )


def build_profit_bridge_table(
    candidates: pd.DataFrame
) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
        
    out = candidates.copy()

    # derive source sell risk ratio from existing columns
    out["source_sell_risk_ratio"] = np.where(
        out["source_stock"] > 0,
        np.minimum(1.0, out["source_forecast_7d"] / out["source_stock"]),
        0.0
    )

    # show transport components if you keep them in candidates
    cols = [
        "product_id",
        "source_store",
        "dest_store",
        "proposed_qty",
        "unit_margin",
        "source_forecast_7d",
        "dest_forecast_7d",
        "destination_gain",
        "source_sell_risk_ratio",
        "source_loss",
        "transport_cost",
        "net_profit",
        "profit_per_unit_transferred"
    ]

    existing_cols = [c for c in cols if c in out.columns]
    return out[existing_cols].sort_values("net_profit", ascending=False)

def build_formula_trace_table(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
        
    rows = []

    for _, row in candidates.iterrows():
        source_sell_risk_ratio = min(1.0, row["source_forecast_7d"] / row["source_stock"]) if row["source_stock"] > 0 else 0.0

        rows.append({
            "product_id": row["product_id"],
            "route": f'{row["source_store"]} -> {row["dest_store"]}',
            "qty_formula": f'min(source transferable, destination need) = {row["proposed_qty"]}',
            "destination_gain_formula": f'{row["proposed_qty"]} * {row["unit_margin"]:.3f} = {row["destination_gain"]:.3f}',
            "source_loss_formula": f'{row["proposed_qty"]} * {source_sell_risk_ratio:.3f} * {row["unit_margin"]:.3f} = {row["source_loss"]:.3f}',
            "transport_formula": f'transport = {row["transport_cost"]:.3f}',
            "net_profit_formula": f'{row["destination_gain"]:.3f} - {row["source_loss"]:.3f} - {row["transport_cost"]:.3f} = {row["net_profit"]:.3f}'
        })

    return pd.DataFrame(rows)