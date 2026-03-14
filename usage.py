import pandas as pd
from forecast import add_last_sale_info, prepare_daily_data, add_features, forecast_next_n_days, build_transfer_signal
from cost_computation import (
    prepare_profit_inputs,
    generate_transfer_candidates,
    build_source_audit_table,
    build_destination_audit_table,
    build_profit_bridge_table,
    build_formula_trace_table
)
# Load your sales file
df = pd.read_csv("sales_inventory.csv")

# Prepare data
df = prepare_daily_data(df)
df = add_features(df)

# Forecast next 7 days starting tomorrow
daily_forecasts, summary = forecast_next_n_days(df, start_date="2026-03-15", horizon=7)

print("=== Daily forecasts ===")
print(daily_forecasts.head())

print("\n=== 7-day summary ===")
print(summary.head())

# Build signals for items that may need transfer review
signals = build_transfer_signal(df, summary, as_of_date="2026-03-15")

print("\n=== Transfer candidate signals ===")
print(signals.head(20))


transfer_costs = pd.DataFrame({
    "from_store": ["S1", "S1", "S2", "S2"],
    "to_store":   ["S2", "S3", "S1", "S3"],
    "transport_cost_fixed": [8, 12, 8, 6],
    "transport_cost_per_unit": [0.5, 0.8, 0.5, 0.4]
})

product_master = pd.DataFrame({
    "product_id": ["P1", "P2", "P3"],
    "unit_sale_price": [25, 12, 40],
    "unit_cost": [15, 7, 26]
})

profit_inputs = prepare_profit_inputs(
    forecast_summary=summary,
    product_master=product_master,
    transfer_costs=transfer_costs,
    safety_days=3.0,
    target_cover_days=7.0
)

last_sale_info = add_last_sale_info(df, as_of_date="2026-03-15")

candidates = generate_transfer_candidates(
    profit_inputs=profit_inputs,
    transfer_costs=transfer_costs,
    days_since_last_sale_df=last_sale_info,
    stale_days_threshold=10,
    risk_cost_per_unit=0.2,
    require_stale_source=True
)

formula_trace = build_formula_trace_table(candidates, risk_cost_per_unit=0.2)

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)
pd.set_option("display.float_format", lambda x: f"{x:,.3f}")

source_audit = build_source_audit_table(
    profit_inputs=profit_inputs,
    days_since_last_sale_df=last_sale_info
)

destination_audit = build_destination_audit_table(
    profit_inputs=profit_inputs
)

profit_bridge = build_profit_bridge_table(
    candidates=candidates,
    risk_cost_per_unit=0.2
)

formula_trace = build_formula_trace_table(
    candidates=candidates,
    risk_cost_per_unit=0.2
)

output_file = "transfer_analysis.xlsx"

with pd.ExcelWriter(output_file, engine="xlsxwriter") as writer:

    daily_forecasts.to_excel(writer, sheet_name="daily_forecasts", index=False)
    summary.to_excel(writer, sheet_name="forecast_summary", index=False)
    signals.to_excel(writer, sheet_name="transfer_signals", index=False)

    source_audit.to_excel(writer, sheet_name="source_audit", index=False)
    destination_audit.to_excel(writer, sheet_name="destination_audit", index=False)

    candidates.to_excel(writer, sheet_name="profit_bridge", index=False)

    formula_trace.to_excel(writer, sheet_name="formula_trace", index=False)

    workbook  = writer.book
    worksheet = writer.sheets["daily_forecasts"]

    number_format = workbook.add_format({'num_format': '#,##0.00'})
    worksheet.set_column("A:H", 18)

print(f"\nExcel report saved to: {output_file}")