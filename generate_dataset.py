# Generate a ~150MB CSV file with synthetic store-product sales data

import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta

output_path = "/mnt/data/big_sales_inventory.csv"

# Parameters to roughly reach ~150MB
rows_per_chunk = 500_000
chunks = 10  # 500k * 10 = 5,000,000 rows total

num_stores = 50
num_products = 200

store_ids = [f"S{i}" for i in range(1, num_stores + 1)]
product_ids = [f"P{i}" for i in range(1, num_products + 1)]

start_date = datetime(2024, 1, 1)
date_range = [start_date + timedelta(days=i) for i in range(365)]

# Remove existing file if present
if os.path.exists(output_path):
    os.remove(output_path)

for chunk_idx in range(chunks):
    dates = np.random.choice(date_range, rows_per_chunk)
    stores = np.random.choice(store_ids, rows_per_chunk)
    products = np.random.choice(product_ids, rows_per_chunk)
    units_sold = np.random.poisson(lam=3, size=rows_per_chunk)
    stock_on_hand = np.random.randint(0, 100, rows_per_chunk)
    
    df = pd.DataFrame({
        "date": dates,
        "store_id": stores,
        "product_id": products,
        "units_sold": units_sold,
        "stock_on_hand": stock_on_hand
    })
    
    df.to_csv(output_path, mode="a", index=False, header=(chunk_idx == 0))

file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
output_path, round(file_size_mb, 2)