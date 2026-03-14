import pandas as pd
import numpy as np


def prepare_daily_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure a complete daily panel for each (store_id, product_id).
    Missing days are filled with 0 sales. Stock is forward-filled if available.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    required_cols = ["date", "store_id", "product_id", "units_sold", "stock_on_hand"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    all_dates = pd.date_range(df["date"].min(), df["date"].max(), freq="D")

    pairs = df[["store_id", "product_id"]].drop_duplicates()

    full_index = pd.MultiIndex.from_product(
        [all_dates, pairs["store_id"].unique(), pairs["product_id"].unique()],
        names=["date", "store_id", "product_id"]
    )

    full_df = pd.DataFrame(index=full_index).reset_index()

    df = full_df.merge(
        df,
        on=["date", "store_id", "product_id"],
        how="left"
    )

    df["units_sold"] = df["units_sold"].fillna(0)

    # Forward-fill stock within each store-product pair, then fill remaining with 0
    df = df.sort_values(["store_id", "product_id", "date"])
    df["stock_on_hand"] = (
        df.groupby(["store_id", "product_id"])["stock_on_hand"]
        .ffill()
        .fillna(0)
    )

    return df


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add forecasting features.
    """
    df = df.copy()
    df["dow"] = df["date"].dt.dayofweek  # Monday=0, Sunday=6

    # A stockout day means observed sales may be artificially low
    df["is_stockout"] = (df["stock_on_hand"] <= 0).astype(int)

    # Use NaN for demand signal on stockout days so they do not pull down averages
    df["effective_sales"] = np.where(df["is_stockout"] == 1, np.nan, df["units_sold"])

    return df


def compute_base_forecast(group: pd.DataFrame, forecast_date: pd.Timestamp) -> float:
    """
    Weighted moving average using the last 28 non-stockout days.
    More recent observations get more weight.
    """
    history = group[group["date"] < forecast_date].sort_values("date").copy()

    if history.empty:
        return 0.0

    # Use last 28 days
    history = history.tail(28)

    # Fill missing effective_sales with NaN, then ignore NaNs in weighted calc
    values = history["effective_sales"].values

    # Recency weights: older -> smaller, recent -> bigger
    weights = np.linspace(1.0, 3.0, num=len(values))

    mask = ~np.isnan(values)
    if mask.sum() == 0:
        return 0.0

    return float(np.average(values[mask], weights=weights[mask]))


def compute_weekday_factor(group: pd.DataFrame, forecast_date: pd.Timestamp) -> float:
    """
    Estimate relative day-of-week behavior.
    If insufficient data, return 1.0.
    """
    history = group[group["date"] < forecast_date].sort_values("date").copy()
    if len(history) < 14:
        return 1.0

    target_dow = forecast_date.dayofweek

    overall_mean = history["effective_sales"].mean(skipna=True)
    dow_mean = history.loc[history["dow"] == target_dow, "effective_sales"].mean(skipna=True)

    if pd.isna(overall_mean) or overall_mean <= 0:
        return 1.0
    if pd.isna(dow_mean):
        return 1.0

    # Clamp to avoid extreme multipliers
    factor = dow_mean / overall_mean
    return float(np.clip(factor, 0.7, 1.3))


def forecast_one_day(df: pd.DataFrame, forecast_date: str) -> pd.DataFrame:
    """
    Forecast next-day demand for each (store_id, product_id).
    """
    forecast_date = pd.to_datetime(forecast_date)
    results = []

    for (store_id, product_id), group in df.groupby(["store_id", "product_id"]):
        base = compute_base_forecast(group, forecast_date)
        dow_factor = compute_weekday_factor(group, forecast_date)
        forecast = max(base * dow_factor, 0.0)

        last_row = group[group["date"] < forecast_date].sort_values("date").tail(1)
        current_stock = float(last_row["stock_on_hand"].iloc[0]) if not last_row.empty else 0.0

        results.append({
            "date": forecast_date,
            "store_id": store_id,
            "product_id": product_id,
            "base_forecast": round(base, 3),
            "dow_factor": round(dow_factor, 3),
            "forecast_units": round(forecast, 3),
            "current_stock": current_stock
        })

    return pd.DataFrame(results)


def forecast_next_n_days(df: pd.DataFrame, start_date: str, horizon: int = 7) -> pd.DataFrame:
    """
    Forecast demand for the next N days independently.
    For a first version, each day is forecast from historical data only.
    """
    start_date = pd.to_datetime(start_date)
    forecasts = []

    for i in range(horizon):
        forecast_date = start_date + pd.Timedelta(days=i)
        day_fc = forecast_one_day(df, forecast_date)
        forecasts.append(day_fc)

    out = pd.concat(forecasts, ignore_index=True)

    summary = (
        out.groupby(["store_id", "product_id"], as_index=False)
        .agg(
            forecast_7d=("forecast_units", "sum"),
            avg_daily_forecast=("forecast_units", "mean"),
            min_daily_forecast=("forecast_units", "min"),
            max_daily_forecast=("forecast_units", "max"),
            current_stock=("current_stock", "last")
        )
    )

    summary["days_of_cover"] = np.where(
        summary["avg_daily_forecast"] > 0,
        summary["current_stock"] / summary["avg_daily_forecast"],
        np.inf
    )

    return out, summary


def add_last_sale_info(df: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
    """
    Add days since last sale per (store_id, product_id).
    """
    as_of_date = pd.to_datetime(as_of_date)
    sold = df[df["units_sold"] > 0].copy()

    last_sales = (
        sold.groupby(["store_id", "product_id"], as_index=False)["date"]
        .max()
        .rename(columns={"date": "last_sale_date"})
    )

    all_pairs = df[["store_id", "product_id"]].drop_duplicates()
    result = all_pairs.merge(last_sales, on=["store_id", "product_id"], how="left")
    result["days_since_last_sale"] = (as_of_date - result["last_sale_date"]).dt.days

    return result


def build_transfer_signal(df: pd.DataFrame, forecast_summary: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
    """
    Create a simple signal for inventory transfer candidates.
    This does NOT optimize transfers; it only flags likely excess stock.
    """
    last_sale = add_last_sale_info(df, as_of_date)

    out = forecast_summary.merge(last_sale, on=["store_id", "product_id"], how="left")

    out["no_sale_10d_flag"] = (out["days_since_last_sale"] >= 10).astype(int)
    out["excess_stock_flag"] = ((out["days_of_cover"] > 14) & (out["no_sale_10d_flag"] == 1)).astype(int)

    return out.sort_values(
        ["excess_stock_flag", "days_of_cover", "days_since_last_sale"],
        ascending=[False, False, False]
    )