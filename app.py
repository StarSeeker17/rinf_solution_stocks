import pandas as pd
import numpy as np
import streamlit as st

from forecast import (
    prepare_daily_data,
    add_features,
    forecast_next_n_days,
    add_last_sale_info,
    build_transfer_signal,
)

from cost_computation import (
    prepare_profit_inputs,
    generate_transfer_candidates,
    build_source_audit_table,
    build_destination_audit_table,
    build_profit_bridge_table,
    build_formula_trace_table,
)


st.set_page_config(
    page_title="Inventory Transfer Optimization Demo",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Inventory Transfer Optimization Demo")
st.caption("Demand forecasting, stale stock detection, and profit-based transfer recommendations")

# -----------------------------
# Sidebar controls
# -----------------------------
st.sidebar.header("Demo Controls")

start_date = st.sidebar.text_input("Forecast start date", value="2026-03-15")
forecast_horizon = st.sidebar.slider("Forecast horizon (days)", min_value=3, max_value=14, value=7)
safety_days = st.sidebar.slider("Safety stock days", min_value=1.0, max_value=10.0, value=3.0, step=0.5)
target_cover_days = st.sidebar.slider("Target cover days", min_value=3.0, max_value=21.0, value=7.0, step=0.5)
stale_days_threshold = st.sidebar.slider("Stale stock threshold (days since last sale)", min_value=5, max_value=60, value=10)
risk_cost_per_unit = st.sidebar.slider("Risk cost per unit", min_value=0.0, max_value=5.0, value=0.2, step=0.1)
require_stale_source = st.sidebar.checkbox("Only allow stale sources", value=True)

st.sidebar.markdown("---")
uploaded_file = st.sidebar.file_uploader("Upload sales CSV", type=["csv"])

# -----------------------------
# Load data
# -----------------------------
@st.cache_data
def load_sales_data(file):
    if file is not None:
        return pd.read_csv(file)
    return pd.read_csv("sales_inventory_10stores_20products.csv")


@st.cache_data
def load_product_master(file):
    if file is not None:
        return pd.read_csv(file)
    return pd.read_csv("product_master.csv")


@st.cache_data
def load_transfer_costs(file):
    if file is not None:
        return pd.read_csv(file)
    return pd.read_csv("transfer_costs.csv")

try:
    raw_df = load_sales_data(uploaded_file)
    product_master = load_product_master(uploaded_file)
    transfer_costs = load_transfer_costs(uploaded_file)
except Exception as e:
    st.error(f"Failed to load input data: {e}")
    st.stop()


# -----------------------------
# Run pipeline
# -----------------------------
try:
    df = prepare_daily_data(raw_df)
    df = add_features(df)

    daily_forecasts, summary = forecast_next_n_days(
        df,
        start_date=start_date,
        horizon=forecast_horizon,
    )

    last_sale_info = add_last_sale_info(df, as_of_date=start_date)

    signals = build_transfer_signal(
        df=df,
        forecast_summary=summary,
        as_of_date=start_date,
    )

    profit_inputs = prepare_profit_inputs(
        forecast_summary=summary,
        product_master=product_master,
        safety_days=safety_days,
        target_cover_days=target_cover_days,
    )

    candidates = generate_transfer_candidates(
        profit_inputs=profit_inputs,
        transfer_costs=transfer_costs,
        days_since_last_sale_df=last_sale_info,
        stale_days_threshold=stale_days_threshold,
        risk_cost_per_unit=risk_cost_per_unit,
        require_stale_source=require_stale_source,
    )

    source_audit = build_source_audit_table(
        profit_inputs=profit_inputs,
        days_since_last_sale_df=last_sale_info,
    )

    destination_audit = build_destination_audit_table(
        profit_inputs=profit_inputs,
    )

    profit_bridge = build_profit_bridge_table(
        candidates=candidates,
        risk_cost_per_unit=risk_cost_per_unit,
    )

    formula_trace = build_formula_trace_table(
        candidates=candidates,
        risk_cost_per_unit=risk_cost_per_unit,
    )

except Exception as e:
    st.error(f"Pipeline execution failed: {e}")
    st.stop()

# -----------------------------
# KPIs
# -----------------------------
st.subheader("Executive Summary")

col1, col2, col3, col4 = st.columns(4)

num_transfer_candidates = 0 if candidates.empty else len(candidates)
total_net_profit = 0.0 if candidates.empty else float(candidates["net_profit"].sum())
total_units = 0 if candidates.empty else int(candidates["proposed_qty"].sum())
num_stale_excess = int(signals["excess_stock_flag"].sum()) if "excess_stock_flag" in signals.columns else 0

col1.metric("Profitable Transfer Routes", num_transfer_candidates)
col2.metric("Projected Net Profit", f"{total_net_profit:,.2f}")
col3.metric("Proposed Units to Move", total_units)
col4.metric("Stale Excess Cases", num_stale_excess)

st.markdown("---")

# -----------------------------
# Filters
# -----------------------------
st.subheader("Filters")

f1, f2, f3 = st.columns(3)

store_options = sorted(summary["store_id"].dropna().unique().tolist())
product_options = sorted(summary["product_id"].dropna().unique().tolist())

selected_stores = f1.multiselect("Filter stores", store_options, default=store_options)
selected_products = f2.multiselect("Filter products", product_options, default=product_options)
min_profit_filter = f3.number_input("Minimum net profit", min_value=0.0, value=0.0, step=1.0)

def filter_df(dataframe, store_cols=None, product_col="product_id"):
    df_filtered = dataframe.copy()
    if product_col in df_filtered.columns:
        df_filtered = df_filtered[df_filtered[product_col].isin(selected_products)]

    if store_cols:
        mask = pd.Series(False, index=df_filtered.index)
        for col in store_cols:
            if col in df_filtered.columns:
                mask = mask | df_filtered[col].isin(selected_stores)
        df_filtered = df_filtered[mask]
    return df_filtered

summary_view = filter_df(summary, store_cols=["store_id"])
signals_view = filter_df(signals, store_cols=["store_id"])
source_view = filter_df(source_audit, store_cols=["source_store"])
destination_view = filter_df(destination_audit, store_cols=["dest_store"])

if not candidates.empty:
    candidates_view = filter_df(candidates, store_cols=["source_store", "dest_store"])
    candidates_view = candidates_view[candidates_view["net_profit"] >= min_profit_filter]
    profit_bridge_view = filter_df(profit_bridge, store_cols=["source_store", "dest_store"])
    profit_bridge_view = profit_bridge_view[profit_bridge_view["net_profit"] >= min_profit_filter]
    formula_trace_view = filter_df(formula_trace, product_col="product_id")
else:
    candidates_view = candidates.copy()
    profit_bridge_view = profit_bridge.copy()
    formula_trace_view = formula_trace.copy()

# -----------------------------
# Tabs
# -----------------------------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Forecast Summary",
    "Transfer Signals",
    "Source vs Destination",
    "Profit Recommendations",
    "Formula Trace",
    "Export",
])

with tab1:
    st.subheader("Forecast Summary")
    st.dataframe(summary_view, use_container_width=True)

    st.subheader("Days of Cover by Store/Product")
    if not summary_view.empty:
        chart_df = summary_view[["store_id", "product_id", "days_of_cover"]].copy()
        chart_df["label"] = chart_df["store_id"] + " - " + chart_df["product_id"]
        st.bar_chart(chart_df.set_index("label")["days_of_cover"])

    st.subheader("Daily Forecast Detail")
    daily_view = filter_df(daily_forecasts, store_cols=["store_id"])
    st.dataframe(daily_view, use_container_width=True)

with tab2:
    st.subheader("Transfer Candidate Signals")
    st.dataframe(signals_view, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        stale_only = signals_view[signals_view["no_sale_10d_flag"] == 1] if "no_sale_10d_flag" in signals_view.columns else pd.DataFrame()
        st.markdown("**Stale Inventory**")
        st.dataframe(stale_only, use_container_width=True)

    with c2:
        excess_only = signals_view[signals_view["excess_stock_flag"] == 1] if "excess_stock_flag" in signals_view.columns else pd.DataFrame()
        st.markdown("**Excess Stock**")
        st.dataframe(excess_only, use_container_width=True)

with tab3:
    st.subheader("Source Audit")
    st.dataframe(source_view, use_container_width=True)

    st.subheader("Destination Audit")
    st.dataframe(destination_view, use_container_width=True)

with tab4:
    st.subheader("Profitable Transfer Recommendations")

    if candidates_view.empty:
        st.info("No profitable transfers found under current assumptions.")
    else:
        top_cols = [
            "product_id",
            "source_store",
            "dest_store",
            "proposed_qty",
            "destination_gain",
            "source_loss",
            "transport_cost",
            "risk_cost",
            "net_profit",
            "profit_per_unit_transferred",
        ]
        available_cols = [c for c in top_cols if c in candidates_view.columns]
        st.dataframe(candidates_view[available_cols], use_container_width=True)

        st.subheader("Profit Bridge")
        st.dataframe(profit_bridge_view, use_container_width=True)

        st.subheader("Top Recommended Route")
        best_row = candidates_view.sort_values("net_profit", ascending=False).iloc[0]

        st.success(
            f"Move {int(best_row['proposed_qty'])} units of {best_row['product_id']} "
            f"from {best_row['source_store']} to {best_row['dest_store']} "
            f"for an expected net profit of {best_row['net_profit']:,.2f}."
        )

with tab5:
    st.subheader("Formula Trace")
    if formula_trace_view.empty:
        st.info("No formula trace available because there are no profitable candidates.")
    else:
        st.dataframe(formula_trace_view, use_container_width=True)

with tab6:
    st.subheader("Export Current Analysis")

    output_tables = {
        "daily_forecasts": daily_forecasts,
        "forecast_summary": summary,
        "transfer_signals": signals,
        "source_audit": source_audit,
        "destination_audit": destination_audit,
        "profit_bridge": profit_bridge,
        "formula_trace": formula_trace,
    }

    st.write("The current analysis can be exported to a multi-sheet Excel file.")

    from io import BytesIO

    def to_excel_bytes(tables_dict):
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            for sheet_name, table in tables_dict.items():
                safe_sheet_name = sheet_name[:31]
                table.to_excel(writer, sheet_name=safe_sheet_name, index=False)
        buffer.seek(0)
        return buffer.getvalue()

    excel_data = to_excel_bytes(output_tables)

    st.download_button(
        label="Download Excel Report",
        data=excel_data,
        file_name="transfer_analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# -----------------------------
# Footer explanation
# -----------------------------
st.markdown("---")
st.markdown(
    """
### How to present this to a client
- **Forecast Summary** shows where demand is expected.
- **Transfer Signals** shows where stock is stale or excessive.
- **Source vs Destination** explains which stores can send and which need stock.
- **Profit Recommendations** proves whether a transfer is worth doing financially.
- **Formula Trace** makes every recommendation auditable.
"""
)