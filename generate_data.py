import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import math

# Configuration
DAYS = 30
START_DATE = datetime(2026, 2, 13)

np.random.seed(42)

# --- 1. Realistic Products (Tech Retailer) ---
products_data = [
    {"id": "P01", "name": "Iphone 15 Pro", "cost": 4200, "price": 5000},
    {"id": "P02", "name": "Iphone 15 Pro Max", "cost": 4800, "price": 5700},
    {"id": "P03", "name": "Samsung Galaxy S24 Ultra", "cost": 4300, "price": 5200},
    {"id": "P04", "name": "Samsung Galaxy A54", "cost": 1200, "price": 1600},
    {"id": "P05", "name": "MacBook Air M2", "cost": 4500, "price": 5300},
    {"id": "P06", "name": "MacBook Pro 14 M3", "cost": 7500, "price": 8600},
    {"id": "P07", "name": "Lenovo IdeaPad 3", "cost": 1500, "price": 2000},
    {"id": "P08", "name": "ASUS ROG Strix G15", "cost": 5500, "price": 6400},
    {"id": "P09", "name": "iPad Air 5th Gen", "cost": 2500, "price": 3100},
    {"id": "P10", "name": "Samsung Tab S9", "cost": 3000, "price": 3700},
    {"id": "P11", "name": "Apple Watch Series 9", "cost": 1700, "price": 2100},
    {"id": "P12", "name": "Samsung Galaxy Watch 6", "cost": 1200, "price": 1500},
    {"id": "P13", "name": "Garmin Fenix 7", "cost": 2800, "price": 3400},
    {"id": "P14", "name": "AirPods Pro 2", "cost": 900, "price": 1200},
    {"id": "P15", "name": "Sony WH-1000XM5", "cost": 1400, "price": 1800},
    {"id": "P16", "name": "Samsung 55-inch 4K TV", "cost": 2200, "price": 2800},
    {"id": "P17", "name": "LG OLED 65-inch TV", "cost": 5000, "price": 6200},
    {"id": "P18", "name": "PlayStation 5", "cost": 2100, "price": 2500},
    {"id": "P19", "name": "Xbox Series X", "cost": 2000, "price": 2400},
    {"id": "P20", "name": "Nintendo Switch OLED", "cost": 1400, "price": 1700},
]

df_products = pd.DataFrame([
    {"product_id": f"{p['name']} ({p['id']})", "unit_cost": p['cost'], "unit_sale_price": p['price']}
    for p in products_data
])
df_products.to_csv("product_master.csv", index=False)

# --- 2. Realistic Romanian Stores & Distances ---
stores_data = {
    "Bucuresti (Baneasa)": {"lat": 44.4268, "lon": 26.1025, "multiplier": 2.5}, #High volume
    "Bucuresti (AFI)": {"lat": 44.4300, "lon": 26.0500, "multiplier": 2.0},
    "Cluj-Napoca": {"lat": 46.7712, "lon": 23.6236, "multiplier": 1.5},
    "Timisoara": {"lat": 45.7489, "lon": 21.2087, "multiplier": 1.2},
    "Iasi": {"lat": 47.1585, "lon": 27.6014, "multiplier": 1.1},
    "Constanta": {"lat": 44.1598, "lon": 28.6348, "multiplier": 1.0},
    "Brasov": {"lat": 45.6427, "lon": 25.5887, "multiplier": 0.9},
    "Craiova": {"lat": 44.3302, "lon": 23.7949, "multiplier": 0.8},
    "Sibiu": {"lat": 45.7983, "lon": 24.1256, "multiplier": 0.6},
    "Oradea": {"lat": 47.0465, "lon": 21.9189, "multiplier": 0.5}, # Low volume
}

# Real approximate driving distances in km 
# Matrix format: (City A, City B): distance_in_km
road_matrix = {
    ("Bucuresti (Baneasa)", "Bucuresti (AFI)"): 12,
    ("Bucuresti (Baneasa)", "Cluj-Napoca"): 450,
    ("Bucuresti (Baneasa)", "Timisoara"): 540,
    ("Bucuresti (Baneasa)", "Iasi"): 390,
    ("Bucuresti (Baneasa)", "Constanta"): 230,
    ("Bucuresti (Baneasa)", "Brasov"): 160,
    ("Bucuresti (Baneasa)", "Craiova"): 240,
    ("Bucuresti (Baneasa)", "Sibiu"): 270,
    ("Bucuresti (Baneasa)", "Oradea"): 590,
    ("Bucuresti (AFI)", "Cluj-Napoca"): 450,
    ("Bucuresti (AFI)", "Timisoara"): 540,
    ("Bucuresti (AFI)", "Iasi"): 390,
    ("Bucuresti (AFI)", "Constanta"): 230,
    ("Bucuresti (AFI)", "Brasov"): 170,
    ("Bucuresti (AFI)", "Craiova"): 230,
    ("Bucuresti (AFI)", "Sibiu"): 270,
    ("Bucuresti (AFI)", "Oradea"): 590,
    ("Cluj-Napoca", "Timisoara"): 320,
    ("Cluj-Napoca", "Iasi"): 390,
    ("Cluj-Napoca", "Constanta"): 680,
    ("Cluj-Napoca", "Brasov"): 270,
    ("Cluj-Napoca", "Craiova"): 400,
    ("Cluj-Napoca", "Sibiu"): 170,
    ("Cluj-Napoca", "Oradea"): 150,
    ("Timisoara", "Iasi"): 690,
    ("Timisoara", "Constanta"): 760,
    ("Timisoara", "Brasov"): 410,
    ("Timisoara", "Craiova"): 330,
    ("Timisoara", "Sibiu"): 270,
    ("Timisoara", "Oradea"): 170,
    ("Iasi", "Constanta"): 430,
    ("Iasi", "Brasov"): 300,
    ("Iasi", "Craiova"): 580,
    ("Iasi", "Sibiu"): 430,
    ("Iasi", "Oradea"): 530,
    ("Constanta", "Brasov"): 390,
    ("Constanta", "Craiova"): 460,
    ("Constanta", "Sibiu"): 490,
    ("Constanta", "Oradea"): 810,
    ("Brasov", "Craiova"): 290,
    ("Brasov", "Sibiu"): 140,
    ("Brasov", "Oradea"): 440,
    ("Craiova", "Sibiu"): 230,
    ("Craiova", "Oradea"): 470,
    ("Sibiu", "Oradea"): 310,
}

def get_driving_distance(city1, city2):
    if city1 == city2:
        return 0
    # Check both directions in the dictionary
    if (city1, city2) in road_matrix:
        return road_matrix[(city1, city2)]
    elif (city2, city1) in road_matrix:
        return road_matrix[(city2, city1)]
    else:
        return 300

transfer_costs = []
stores = list(stores_data.keys())

for s_from in stores:
    for s_to in stores:
        if s_from != s_to:
            dist_km = get_driving_distance(s_from, s_to)

            # Realistic Insured Tech Frieght
            # Base dispatch fee: 40 RON
            # Distance fee: 0.8 RON per km
            fixed_cost = 40.0 + (dist_km * 0.8)

            # Per unit insurance and handling based on it being tech
            # A MacBook costs more to insure in a van than a t-shirt.
            per_unit_cost = 15.0

            transfer_costs.append({
                "from_store": s_from,
                "to_store": s_to,
                "transport_cost_fixed": round(fixed_cost, 2),
                "transport_cost_per_unit": round(per_unit_cost, 2)
            })

df_transfer_costs = pd.DataFrame(transfer_costs)
df_transfer_costs.to_csv("transfer_costs.csv", index=False)

# --- 3. Generate Sales & Inventory Data ---
sales_inventory = []

for s in stores:
    store_mult = stores_data[s]["multiplier"]

    for p in df_products["product_id"]:
        # Assign product behavior
        if "TV" in p or "OLED" in p: # Big items don't sell as fast
            base_daily_demand = np.random.uniform(0.1, 0.4) * store_mult
            behavior_type = 1
            current_stock = np.random.randint(5, 20)
        elif "iPhone" in p or "Galaxy" in p: # Fast movers
            base_daily_demand = np.random.uniform(1.0, 4.0) * store_mult
            behavior_type = 2
            current_stock = np.random.randint(15, 60)
        else: # Standard
            base_daily_demand = np.random.uniform(0.2, 1.5) * store_mult
            behavior_type = np.random.choice([0, 1, 2], p=[0.1, 0.6, 0.3])

            if behavior_type == 0: # Dead stock
                base_daily_demand = 0.05
                current_stock = np.random.randint(10, 30)
            else:
                current_stock = np.random.randint(10, 40)
        
        for day in range(DAYS):
            current_date = START_DATE + timedelta(days=day)
            dow_mult = 1.4 if current_date.weekday() >= 5 else 1.0 # Weekend boost

            expected_demand = base_daily_demand * dow_mult
            actual_demand = np.random.poisson(expected_demand) if expected_demand > 0 else 0

            units_sold = min(actual_demand, current_stock)
            
            # Only record if we sold something, or if it's the very last day (to ensure we know final stock)
            if units_sold > 0 or day == DAYS - 1:
                sales_inventory.append({
                    "date": current_date.strftime("%Y-%m-%d"),
                    "store_id": s,
                    "product_id": p,
                    "units_sold": units_sold,
                    "stock_on_hand": current_stock
                })

            current_stock -= units_sold

            # Restock logic
            if behavior_type > 0 and current_stock < 5 and np.random.random() < 0.1:
                current_stock += np.random.randint(10, 30)

df_sales = pd.DataFrame(sales_inventory)
# We overwrite the specific name expected by the app.py
df_sales.to_csv("sales_inventory.csv", index=False)

print("Generated Retail Dataset")
print("Saved to: product_master.csv, transfer_costs.csv, sales_inventory_10stores_20products.csv")