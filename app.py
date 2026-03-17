import pandas as pd
import numpy as np
import streamlit as st
import altair as alt

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
    choose_best_non_conflicting_transfers,
)

def humanize_days_since_last_sale(df):
    """
    For display purposes:
    - Keep numeric 'days_since_last_sale' column for all math.
    - Add 'days_since_last_sale_display' for the UI.
    """

    out = df.copy()
    if "days_since_last_sale" in out.columns:
        out["days_since_last_sale_display"] = out["days_since_last_sale"].replace(999, np.nan)
    return out

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
safety_days = st.sidebar.slider("Safety stock days", min_value=1.0, max_value=10.0, value=3.0, step=0.5)
target_cover_days = st.sidebar.slider("Target cover days", min_value=3.0, max_value=21.0, value=7.0, step=0.5)
stale_days_threshold = st.sidebar.slider("Stale stock threshold (days since last sale)", min_value=5, max_value=60, value=10, step=1)
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
    return pd.read_csv("sales_inventory.csv")


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
        horizon=7,
    )

    last_sale_info = add_last_sale_info(df, as_of_date=start_date)

    signals = build_transfer_signal(
        df=df,
        forecast_summary=summary,
        as_of_date=start_date,
        stale_days_threshold=stale_days_threshold,
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
        require_stale_source=require_stale_source,
    )
    
    candidates = choose_best_non_conflicting_transfers(candidates)

    source_audit = build_source_audit_table(
        profit_inputs=profit_inputs,
        days_since_last_sale_df=last_sale_info,
    )

    destination_audit = build_destination_audit_table(
        profit_inputs=profit_inputs,
    )

    profit_bridge = build_profit_bridge_table(
        candidates=candidates
    )

    formula_trace = build_formula_trace_table(
        candidates=candidates
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

st.caption(
    "Transfers are only proposed if they keep at least 10 units of stock in the source store."
    "and generate a positive net profit after logistics and lost sales risk."
)

st.markdown("---")

table_formatting = {
    "product_id": st.column_config.TextColumn("Product"),
    "store_id": st.column_config.TextColumn("Store"),
    "source_store": st.column_config.TextColumn("Source Store"),
    "dest_store": st.column_config.TextColumn("Dest Store"),
    "current_stock": st.column_config.NumberColumn("Current Stock", format="%d"),
    "source_stock": st.column_config.NumberColumn("Source Stock", format="%d"),
    "dest_stock": st.column_config.NumberColumn("Dest Stock", format="%d"),
    "avg_daily_forecast": st.column_config.NumberColumn("Daily Forecast", format="%.2f"),
    "source_avg_daily_forecast": st.column_config.NumberColumn("Daily Forecast", format="%.2f"),
    "dest_avg_daily_forecast": st.column_config.NumberColumn("Daily Forecast", format="%.2f"),
    "forecast_7d": st.column_config.NumberColumn("7D Forecast", format="%.1f"),
    "source_forecast_7d": st.column_config.NumberColumn("7D Forecast", format="%.1f"),
    "dest_forecast_7d": st.column_config.NumberColumn("7D Forecast", format="%.1f"),
    "days_of_cover": st.column_config.NumberColumn("Days of Cover", format="%.1f"),
    "source_days_of_cover": st.column_config.NumberColumn("Days of Cover", format="%.1f"),
    "dest_days_of_cover": st.column_config.NumberColumn("Days of Cover", format="%.1f"),
    "days_since_last_sale": st.column_config.NumberColumn("Days Since Sale", format="%d"),
    "days_since_last_sale_display": st.column_config.NumberColumn("Days Since Sale", format="%d"),
    "source_days_since_last_sale": st.column_config.NumberColumn("Days Since Sale", format="%d"),
    "sold_last_30d": st.column_config.NumberColumn("Sold (30d)", format="%d"),
    "safety_stock": st.column_config.NumberColumn("Safety Stock", format="%d"),
    "target_stock": st.column_config.NumberColumn("Target Stock", format="%d"),
    "transferable_units": st.column_config.NumberColumn("Transferable Stock", format="%d"),
    "max_transferable_units": st.column_config.NumberColumn("Max Transferable", format="%d"),
    "needed_units": st.column_config.NumberColumn("Needed Stock", format="%d"),
    "max_needed_units": st.column_config.NumberColumn("Max Needed", format="%d"),
    "proposed_qty": st.column_config.NumberColumn("Proposed Qty", format="%d"),
    "unit_cost": st.column_config.NumberColumn("Unit Cost (RON)", format="%.2f"),
    "unit_sale_price": st.column_config.NumberColumn("Unit Price (RON)", format="%.2f"),
    "unit_margin": st.column_config.NumberColumn("Unit Margin (RON)", format="%.2f"),
    "destination_gain": st.column_config.NumberColumn("Dest Gain (RON)", format="%.2f"),
    "source_loss": st.column_config.NumberColumn("Source Loss (RON)", format="%.2f"),
    "transport_cost": st.column_config.NumberColumn("Transport Cost (RON)", format="%.2f"),
    "net_profit": st.column_config.NumberColumn("Net Profit (RON)", format="%.2f"),
    "profit_per_unit_transferred": st.column_config.NumberColumn("Profit per Unit", format="%.2f"),
    "excess_stock_flag": st.column_config.CheckboxColumn("Excess Stock?"),
    "stale_stock_flag": st.column_config.CheckboxColumn("Stale Stock?"),
    "low_quantity_flag": st.column_config.CheckboxColumn("Low Qty (<5)?")
}

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
summary_view = humanize_days_since_last_sale(summary_view)

signals_view = filter_df(signals, store_cols=["store_id"])
signals_view = humanize_days_since_last_sale(signals_view)

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
    st.dataframe(summary_view, use_container_width=True, column_config=table_formatting)

    st.subheader("Interactive Stock Health Visualizations")
    if not summary_view.empty:
        # 1. The Toggle Switch
        chart_type = st.radio(
            "Select Perspective:",
            ["Top 15 Worst Offenders (Overstocked)", "Average Days of Cover by Store", " Scatter: Stock vs Daily Sales"],
            horizontal=True
        )

        # 2. Logic for Graph 1: Top 15 Highest Days of Cover
        if chart_type == "Top 15 Worst Offenders (Overstocked)":
            # Temporarily replace 'Infinity' with 999 so the graph doesn't crash on dead stock
            overstock_df = summary_view.replace([np.inf, -np.inf], 999).sort_values("days_of_cover",
            ascending=False).head(15)
            overstock_df["label"] = overstock_df["store_id"] + " - " + overstock_df["product_id"]

            # Draw horizontal Bar Chart
            c = alt.Chart(overstock_df).mark_bar(color="#ff4b4b").encode(
                x=alt.X("days_of_cover:Q", title="Days of Cover (999 = Infinity/Dead)"),
                y=alt.Y("label:N", sort="-x", title="Store & Product"),
                tooltip=["store_id", "product_id", "days_of_cover", "current_stock"]
            ).properties(height=400)
            st.altair_chart(c, use_container_width=True)
            
        # 3. Logic for Graph 2: Store Averages
        elif chart_type == "Average Days of Cover by Store":
            # Ignore completely dead stock when calculating averages
            store_avg = summary_view.replace([np.inf, -np.inf], np.nan).groupby("store_id", as_index=False)["days_of_cover"].mean()

            c = alt.Chart(store_avg).mark_bar(color="#4b8bff").encode(
                x=alt.X("days_of_cover:Q", title="Average Days of Cover"),
                y=alt.Y("store_id:N", sort="-x", title="Store"),
                tooltip=["store_id", "days_of_cover"]
            ).properties(height=400)
            st.altair_chart(c, use_container_width=True)
            
        # 4. Logic for Graph 3: The Scatter Plot Map
        else:
            # Replace infinity so the dots stay on the screen
            scatter_df = summary_view.replace([np.inf, -np.inf], 999)

            c = alt.Chart(scatter_df).mark_circle(size=80, opacity=0.7).encode(
                x=alt.X("current_stock:Q", title="Current Physical Stock on Shelf"),
                y=alt.Y("avg_daily_forecast:Q", title="Predicted Speed of Sale (units/day)"),
                color=alt.Color("store_id:N", legend=alt.Legend(title="Store Location")),
                tooltip=["store_id", "product_id", "current_stock", "avg_daily_forecast", "days_of_cover"]).interactive().properties(height=450)
                
            st.altair_chart(c, use_container_width=True)
            st.caption(" **How to read:** Bottom Right = Huge Stock & Zero Sales (Overstocked). Top Left = Low Stock & High Sales (Risk of Stockout).")

                

    with st.expander("Daily Forecast Detail (day-by-day breakdown)"):
        st.caption(
            "Forecast per day for the next 7 days. The summary table above shows the 7 day total and average."
        )
        daily_view = filter_df(daily_forecasts, store_cols=["store_id"])
        st.dataframe(daily_view, use_container_width=True, column_config=table_formatting)

with tab2:
    st.subheader("Transfer Candidate Signals")
    st.dataframe(signals_view, use_container_width=True, column_config=table_formatting)

    c1, c2 = st.columns(2)
    with c1:
        stale_only = signals_view[signals_view["stale_stock_flag"] == 1] if "stale_stock_flag" in signals_view.columns else pd.DataFrame()
        st.markdown("**Stale Inventory**")
        st.dataframe(stale_only, use_container_width=True, column_config=table_formatting)

    with c2:
        excess_only = signals_view[signals_view["excess_stock_flag"] == 1] if "excess_stock_flag" in signals_view.columns else pd.DataFrame()
        st.markdown("**Excess Stock**")
        st.dataframe(excess_only, use_container_width=True, column_config=table_formatting)

with tab3:
    st.subheader("Source Audit")
    st.caption(
        "Stores and products that have stock above safety level and can act as senders."
        "Only these appear as possible sources in the profit recommendations."
    )
    st.dataframe(source_view, use_container_width=True, column_config=table_formatting)

    st.subheader("Destination Audit")
    st.caption(
        "Stores and products below target cover that need more stock. "
        "Only these appear as possible destinations in the profit recommendations. "
    )
    st.dataframe(destination_view, use_container_width=True, column_config=table_formatting)

with tab4:
    if candidates_view.empty:
        st.info("No profitable transfers found under current assumptions.")
    else:
        st.subheader("Top Recommended Route")
        best_row = candidates_view.sort_values("net_profit", ascending=False).iloc[0]

        st.success(
            f"Move {int(best_row['proposed_qty'])} units of {best_row['product_id']} "
            f"from {best_row['source_store']} to {best_row['dest_store']} "
            f"for an expected net profit of {best_row['net_profit']:,.2f}."
        )

        st.markdown("---")
        st.subheader("Interactive Profit Comparison")
        st.write("Visually compare the financial outcome of executing a transfer vs doing nothing.")
        
        # Create a human-readable list of proposed transfers for the dropdown
        bridge_options = profit_bridge_view.copy()
        bridge_options['route_label'] = bridge_options['product_id'] + " | " + bridge_options['source_store'] + " ➔ " + bridge_options['dest_store']
        
        selected_route_label = st.selectbox("Select a proposed transfer to analyze:", bridge_options['route_label'].tolist())
        
        if selected_route_label:
            # Get the specific row data
            selected_row = bridge_options[bridge_options['route_label'] == selected_route_label].iloc[0]
            
            # The 'Do Nothing' scenario:
            do_nothing_profit = selected_row['source_loss']
            
            # The 'Execute Transfer' scenario:
            execute_transfer_profit = selected_row['destination_gain'] - selected_row['transport_cost']
            
            # Build chart data
            chart_data = pd.DataFrame({
                "Scenario": ["Do Nothing (Keep at Source)", "Execute Transfer"],
                "Total Expected Profit (RON)": [do_nothing_profit, execute_transfer_profit]
            })
            
            c1, c2 = st.columns([1, 2])
            with c1:
                st.write("**Transfer Math breakdown:**")
                st.write(f"- Quantity Moving: **{int(selected_row['proposed_qty'])}**")
                st.write(f"- Source 7D Forecast: **{selected_row['source_forecast_7d']:,.1f} units**")
                st.write(f"- Dest 7D Forecast: **{selected_row['dest_forecast_7d']:,.1f} units**")
                st.write(f"- Margin per Unit: **{selected_row['unit_margin']:,.2f} RON**")
                st.write(f"- Gross Gain at Dest: **{selected_row['destination_gain']:,.2f} RON**")
                st.write(f"- Transport Costs: **-{selected_row['transport_cost']:,.2f} RON**")
                
            with c2:
                # Horizontal bar chart with contrasting colors based on scenario
                chart = alt.Chart(chart_data).mark_bar(
                    cornerRadiusTopRight=5, 
                    cornerRadiusBottomRight=5,
                    height=50
                ).encode(
                    x=alt.X("Total Expected Profit (RON):Q", title="Net Profit (RON)"),
                    y=alt.Y("Scenario:N", sort=["Do Nothing (Keep at Source)", "Execute Transfer"], title="", axis=alt.Axis(labelAngle=0, labelLimit=200)),
                    color=alt.Color("Scenario:N", scale=alt.Scale(range=["#ff4b4b", "#09ab3b"]), legend=None),
                    tooltip=["Scenario", "Total Expected Profit (RON)"]
                ).properties(height=250)
                st.altair_chart(chart, use_container_width=True)

        st.markdown("---")
        st.subheader("All Candidate Transfers")
        st.caption(
            "Each proposed route moves stock from a store with excess or stale inventory to a store"
            "with demonstrated demand, only when the expected destination margin minus source risk"
            "and transport cost results in positive net profit."
        )

        top_cols = [
            "product_id",
            "stale_stock_flag",
            "source_store",
            "dest_store",
            "proposed_qty",
            "destination_gain",
            "source_loss",
            "transport_cost",
            "net_profit",
            "profit_per_unit_transferred",
        ]
        available_cols = [c for c in top_cols if c in candidates_view.columns]
        st.dataframe(candidates_view[available_cols], use_container_width=True, column_config=table_formatting)

        st.subheader("Profit Bridge")
        st.dataframe(profit_bridge_view, use_container_width=True, column_config=table_formatting)

with tab5:
    st.subheader("Formula Trace")
    if formula_trace_view.empty:
        st.info("No formula trace available because there are no profitable candidates.")
    else:
        st.dataframe(formula_trace_view, use_container_width=True, column_config=table_formatting)

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