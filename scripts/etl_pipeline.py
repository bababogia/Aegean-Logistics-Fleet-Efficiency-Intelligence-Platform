import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

# ------------------------------------------------------------------------------
# Configuration & Database Connection
# ------------------------------------------------------------------------------
from pathlib import Path

# Set paths dynamically relative to repository root
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"

RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
# PostgreSQL Connection String (Update local credentials)
DB_URI = "postgresql://postgres:"yourpassword"@localhost:5432/my_database"

def parse_mixed_timestamps(series):
    """Parses timestamps formatted in inconsistent formats across raw records."""
    return pd.to_datetime(series, format='mixed', errors='coerce')

def run_etl():
    print("--- Phase 2 ETL Pipeline Initialized ---")
    
    # 1. Load Raw Datasets
    shipments_raw = pd.read_csv(f"{RAW_DATA_DIR}/raw_shipments.csv")
    weather_raw = pd.read_csv(f"{RAW_DATA_DIR}/raw_weather.csv")

    # --------------------------------------------------------------------------
    # 2. Clean & Standardize Shipments
    # --------------------------------------------------------------------------
    print("Cleaning shipment records...")
    df_shipments = shipments_raw.copy()

    # Parse heterogeneous timestamps
    time_cols = ["Scheduled Departure", "Actual Departure", "Scheduled Arrival", "Actual Arrival"]
    for col in time_cols:
        df_shipments[col] = parse_mixed_timestamps(df_shipments[col])

    # Data Quality Rules:
    # Rule A: Remove invalid negative cargo weight anomalies
    df_shipments = df_shipments[df_shipments["Cargo Weight"] >= 0].copy()

    # Rule B: Calculate delays in minutes
    df_shipments["dep_delay_minutes"] = (
        (df_shipments["Actual Departure"] - df_shipments["Scheduled Departure"]).dt.total_seconds() / 60.0
    ).round(1)
    
    df_shipments["arr_delay_minutes"] = (
        (df_shipments["Actual Arrival"] - df_shipments["Scheduled Arrival"]).dt.total_seconds() / 60.0
    ).round(1)

    # Rule C: Operational On-Time Flags (Threshold: <= 15 minutes)
    df_shipments["is_ontime_dep"] = df_shipments["dep_delay_minutes"] <= 15.0
    df_shipments["is_ontime_arr"] = df_shipments["arr_delay_minutes"] <= 15.0

    # --------------------------------------------------------------------------
    # 3. Extract & Build Dimensions
    # --------------------------------------------------------------------------
    print("Generating Star Schema Dimensions...")
    
    # Dim_Ports
    unique_ports = sorted(list(set(df_shipments["Origin Port"]).union(set(df_shipments["Destination Port"]))))
    dim_ports = pd.DataFrame({
        "port_id": range(1, len(unique_ports) + 1),
        "port_name": unique_ports,
        "country": "Greece",
        "region": ["Attica" if p == "Piraeus" else "Crete" if p == "Heraklion" else "Macedonia" if p == "Thessaloniki" else "Aegean Islands" for p in unique_ports]
    })

    port_map = dict(zip(dim_ports["port_name"], dim_ports["port_id"]))
    df_shipments["origin_port_id"] = df_shipments["Origin Port"].map(port_map)
    df_shipments["dest_port_id"] = df_shipments["Destination Port"].map(port_map)

    # Dim_Vessels
    vessels_unique = df_shipments["Vessel Name"].unique()
    dim_vessels = pd.DataFrame({
        "vessel_id": range(1, len(vessels_unique) + 1),
        "vessel_name": vessels_unique,
        "type": "Ro-Ro / Cargo Vessel"
    })
    vessel_map = dict(zip(dim_vessels["vessel_name"], dim_vessels["vessel_id"]))
    df_shipments["vessel_id"] = df_shipments["Vessel Name"].map(vessel_map)

    # Dim_Date (Covering full year timeline)
    min_date = df_shipments["Scheduled Departure"].min().floor("D")
    max_date = df_shipments["Scheduled Departure"].max().ceil("D")
    date_range = pd.date_range(start=min_date, end=max_date, freq="D")
    
    dim_date = pd.DataFrame({
        "date_key": date_range.strftime("%Y%m%d").astype(int),
        "full_date": date_range.date,
        "year": date_range.year,
        "quarter": date_range.quarter,
        "month": date_range.month,
        "month_name": date_range.strftime("%B"),
        "day": date_range.day,
        "day_of_week": date_range.strftime("%A"),
        "is_weekend": date_range.dayofweek >= 5
    })

    # Map Date Keys to Fact Table
    df_shipments["sched_dep_date_key"] = df_shipments["Scheduled Departure"].dt.strftime("%Y%m%d").astype(float).astype("Int64")

    # --------------------------------------------------------------------------
    # 4. Clean Weather Dimension Data
    # --------------------------------------------------------------------------
    weather_raw["Date"] = pd.to_datetime(weather_raw["Date"]).dt.date
    weather_raw["port_id"] = weather_raw["Port Name"].map(port_map)
    
    # Impute missing wind speed values with monthly average per port
    weather_raw["Wind Speed Knots"] = weather_raw.groupby(["port_id", pd.to_datetime(weather_raw["Date"]).dt.month])["Wind Speed Knots"].transform(lambda x: x.fillna(x.mean()))
    
    dim_weather = weather_raw[["Date", "port_id", "Wind Speed Knots", "Sea State Beaufort"]].copy()
    dim_weather.rename(columns={
        "Date": "weather_date",
        "Wind Speed Knots": "wind_speed_knots",
        "Sea State Beaufort": "sea_state_beaufort"
    }, inplace=True)
    dim_weather.insert(0, "weather_id", range(1, len(dim_weather) + 1))

    # --------------------------------------------------------------------------
    # 5. Build Fact Table (Fact_Shipments)
    # --------------------------------------------------------------------------
    fact_shipments = pd.DataFrame({
        "shipment_id": df_shipments["Shipment ID"],
        "vessel_id": df_shipments["vessel_id"],
        "origin_port_id": df_shipments["origin_port_id"],
        "dest_port_id": df_shipments["dest_port_id"],
        "sched_dep_date_key": df_shipments["sched_dep_date_key"],
        "sched_dep_timestamp": df_shipments["Scheduled Departure"],
        "actual_dep_timestamp": df_shipments["Actual Departure"],
        "sched_arr_timestamp": df_shipments["Scheduled Arrival"],
        "actual_arr_timestamp": df_shipments["Actual Arrival"],
        "cargo_weight_ton": df_shipments["Cargo Weight"],
        "fuel_consumed_liters": df_shipments["Fuel Consumed Liters"],
        "dep_delay_minutes": df_shipments["dep_delay_minutes"],
        "arr_delay_minutes": df_shipments["arr_delay_minutes"],
        "is_ontime_dep": df_shipments["is_ontime_dep"],
        "is_ontime_arr": df_shipments["is_ontime_arr"]
    })

    # Export Processed Datasets to CSV (Backup)
    dim_ports.to_csv(f"{PROCESSED_DATA_DIR}/dim_ports.csv", index=False)
    dim_vessels.to_csv(f"{PROCESSED_DATA_DIR}/dim_vessels.csv", index=False)
    dim_date.to_csv(f"{PROCESSED_DATA_DIR}/dim_date.csv", index=False)
    dim_weather.to_csv(f"{PROCESSED_DATA_DIR}/dim_weather.csv", index=False)
    fact_shipments.to_csv(f"{PROCESSED_DATA_DIR}/fact_shipments.csv", index=False)

    print("ETL Transformation complete. CSV files saved to data/processed/")

    # --------------------------------------------------------------------------
    # 6. Database Load into PostgreSQL
    # --------------------------------------------------------------------------
    try:
        engine = create_engine(DB_URI)
        dim_ports.to_sql("dim_ports", engine, if_exists="append", index=False)
        dim_vessels.to_sql("dim_vessels", engine, if_exists="append", index=False)
        dim_date.to_sql("dim_date", engine, if_exists="append", index=False)
        dim_weather.to_sql("dim_weather", engine, if_exists="append", index=False)
        fact_shipments.to_sql("fact_shipments", engine, if_exists="append", index=False)
        print("Data successfully loaded into PostgreSQL tables!")
    except Exception as e:
        print(f"Skipped DB direct insert (Check connection settings or run SQL DDL script first): {e}")

if __name__ == "__main__":
    run_etl()