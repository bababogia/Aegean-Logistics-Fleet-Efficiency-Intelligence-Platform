import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

# Set random seeds for reproducible data generation
fake = Faker()
Faker.seed(42)
np.random.seed(42)
random.seed(42)

# Keep output paths stable regardless of the current working directory.
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------------------
# Master Reference Data (Aegean Shipping Context)
# ------------------------------------------------------------------------------
PORTS = ["Piraeus", "Heraklion", "Thessaloniki", "Rhodes", "Mykonos", "Santorini", "Patras", "Volos"]
VESSELS = [
    {"name": "Aegean Star", "max_capacity_ton": 12000, "base_fuel_per_km": 42.0},
    {"name": "Blue Wave", "max_capacity_ton": 8500, "base_fuel_per_km": 35.5},
    {"name": "Hellenic Trader", "max_capacity_ton": 15000, "base_fuel_per_km": 50.0},
    {"name": "Cyclades Carrier", "max_capacity_ton": 6000, "base_fuel_per_km": 28.0},
    {"name": "Minoan Runner", "max_capacity_ton": 10000, "base_fuel_per_km": 38.0},
    {"name": "Poseidon Express", "max_capacity_ton": 18000, "base_fuel_per_km": 55.0},
]

# Approximate nautical distances (in Nautical Miles)
PORT_DISTANCES_NM = {
    ("Piraeus", "Heraklion"): 174,
    ("Piraeus", "Mykonos"): 94,
    ("Piraeus", "Santorini"): 128,
    ("Piraeus", "Rhodes"): 240,
    ("Thessaloniki", "Heraklion"): 370,
    ("Thessaloniki", "Piraeus"): 250,
    ("Patras", "Heraklion"): 310,
    ("Volos", "Mykonos"): 140,
}

# ------------------------------------------------------------------------------
# 1. Generate Raw Weather Data (`raw_weather.csv`)
# ------------------------------------------------------------------------------
def generate_weather_data(start_date, end_date):
    print("Generating raw weather data...")
    records = []
    current_date = start_date

    while current_date <= end_date:
        for port in PORTS:
            month = current_date.month
            
            # Simulated seasonal Aegean Meltemi winds (higher wind/Beaufort during Jul-Aug and Winter)
            if month in [7, 8]:
                beaufort = np.random.choice([3, 4, 5, 6, 7, 8], p=[0.1, 0.2, 0.3, 0.25, 0.1, 0.05])
            elif month in [12, 1, 2]:
                beaufort = np.random.choice([3, 4, 5, 6, 7, 8, 9], p=[0.05, 0.15, 0.25, 0.3, 0.15, 0.08, 0.02])
            else:
                beaufort = np.random.choice([1, 2, 3, 4, 5, 6], p=[0.15, 0.25, 0.3, 0.2, 0.08, 0.02])

            # Convert Beaufort scale roughly to wind speed in knots
            wind_speed = round(beaufort * 3.5 + np.random.uniform(-2, 2), 1)

            records.append({
                "Date": current_date.strftime("%Y-%m-%d"),
                "Port Name": port,
                "Wind Speed Knots": wind_speed if random.random() > 0.02 else None, # 2% missing values
                "Sea State Beaufort": beaufort
            })
        current_date += timedelta(days=1)

    df_weather = pd.DataFrame(records)
    return df_weather

# ------------------------------------------------------------------------------
# 2. Generate Raw Shipments Data (`raw_shipments.csv`)
# ------------------------------------------------------------------------------
def generate_shipments_data(num_records, start_date, end_date, weather_lookup):
    print("Generating raw shipment records with operational anomalies...")
    records = []

    for idx in range(1, num_records + 1):
        shipment_id = f"SHIP-{10000 + idx}"
        vessel = random.choice(VESSELS)
        
        origin, dest = random.sample(PORTS, 2)
        distance = PORT_DISTANCES_NM.get((origin, dest), PORT_DISTANCES_NM.get((dest, origin), random.randint(100, 300)))
        
        # Scheduled Timestamps
        sched_dep_dt = fake.date_time_between_dates(datetime_start=start_date, datetime_end=end_date)
        avg_speed_knots = 18.0
        est_duration_hours = distance / avg_speed_knots
        sched_arr_dt = sched_dep_dt + timedelta(hours=est_duration_hours)

        # Lookup weather at origin on departure date
        date_str = sched_dep_dt.strftime("%Y-%m-%d")
        weather_row = weather_lookup[(weather_lookup["Port Name"] == origin) & (weather_lookup["Date"] == date_str)]
        beaufort = weather_row["Sea State Beaufort"].values[0] if not weather_row.empty else 3

        # Delay logic based on Beaufort Scale
        delay_minutes = 0
        if beaufort >= 8:
            delay_minutes = random.randint(360, 1440)  # Severe delay (6-24 hours)
        elif beaufort >= 6:
            delay_minutes = random.randint(60, 300)    # Moderate delay (1-5 hours)
        elif random.random() < 0.15:
            delay_minutes = random.randint(15, 90)     # Minor port congestion delay

        actual_dep_dt = sched_dep_dt + timedelta(minutes=random.randint(0, 45) if delay_minutes == 0 else delay_minutes)
        actual_arr_dt = sched_arr_dt + timedelta(minutes=delay_minutes + random.randint(-15, 45))

        # Cargo weight and Fuel consumption modeling
        cargo_weight = round(random.uniform(0.3, 0.95) * vessel["max_capacity_ton"], 2)
        fuel_consumed = round((distance * vessel["base_fuel_per_km"]) * (1 + (cargo_weight / vessel["max_capacity_ton"]) * 0.2) * (1 + (beaufort * 0.05)), 2)

        # ----------------------------------------------------------------------
        # Inject Real-World Messy Data / Anomalies
        # ----------------------------------------------------------------------
        # Format timestamps inconsistently across rows
        date_format_choice = random.random()
        if date_format_choice < 0.70:
            s_dep = sched_dep_dt.strftime("%Y-%m-%d %H:%M:%S")
            a_dep = actual_dep_dt.strftime("%Y-%m-%d %H:%M:%S")
            s_arr = sched_arr_dt.strftime("%Y-%m-%d %H:%M:%S")
            a_arr = actual_arr_dt.strftime("%Y-%m-%d %H:%M:%S")
        elif date_format_choice < 0.88:
            s_dep = sched_dep_dt.strftime("%d/%m/%Y %H:%M")
            a_dep = actual_dep_dt.strftime("%d/%m/%Y %H:%M")
            s_arr = sched_arr_dt.strftime("%d/%m/%Y %H:%M")
            a_arr = actual_arr_dt.strftime("%d/%m/%Y %H:%M")
        else:
            s_dep = sched_dep_dt.strftime("%Y/%m/%d %I:%M %p")
            a_dep = actual_dep_dt.strftime("%Y/%m/%d %I:%M %p")
            s_arr = sched_arr_dt.strftime("%Y/%m/%d %I:%M %p")
            a_arr = actual_arr_dt.strftime("%Y/%m/%d %I:%M %p")

        # Inject NULLs in Actual Arrivals (simulating in-transit or missing telemetry)
        if random.random() < 0.03:
            a_arr = None
            fuel_consumed = None

        # Inject negative or zero cargo noise (0.5% anomalies to clean in SQL)
        if random.random() < 0.005:
            cargo_weight = -100.0

        records.append({
            "Shipment ID": shipment_id,
            "Vessel Name": vessel["name"],
            "Origin Port": origin,
            "Destination Port": dest,
            "Scheduled Departure": s_dep,
            "Actual Departure": a_dep,
            "Scheduled Arrival": s_arr,
            "Actual Arrival": a_arr,
            "Cargo Weight": cargo_weight,
            "Fuel Consumed Liters": fuel_consumed
        })

    return pd.DataFrame(records)

# ------------------------------------------------------------------------------
# Main Execution
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    start_date = datetime(2025, 1, 1)
    end_date = datetime(2025, 12, 31)

    df_weather = generate_weather_data(start_date, end_date)
    df_shipments = generate_shipments_data(3500, start_date, end_date, df_weather)

    # Save to CSV
    weather_path = OUTPUT_DIR / "raw_weather.csv"
    shipments_path = OUTPUT_DIR / "raw_shipments.csv"

    df_weather.to_csv(weather_path, index=False)
    df_shipments.to_csv(shipments_path, index=False)

    print(f"\nSuccessfully generated dataset:")
    print(f" -> Raw Weather: {len(df_weather)} records -> {weather_path}")
    print(f" -> Raw Shipments: {len(df_shipments)} records -> {shipments_path}")