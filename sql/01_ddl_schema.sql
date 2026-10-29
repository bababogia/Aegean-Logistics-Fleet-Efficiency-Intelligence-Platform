-- PostgreSQL Star Schema DDL
-- Database: aegean_logistics

DROP TABLE IF EXISTS fact_shipments CASCADE;
DROP TABLE IF EXISTS dim_weather CASCADE;
DROP TABLE IF EXISTS dim_date CASCADE;
DROP TABLE IF EXISTS dim_vessels CASCADE;
DROP TABLE IF EXISTS dim_ports CASCADE;

-- 1. Dim_Ports
CREATE TABLE dim_ports (
    port_id INT PRIMARY KEY,
    port_name VARCHAR(50) NOT NULL UNIQUE,
    country VARCHAR(50) NOT NULL,
    region VARCHAR(50) NOT NULL
);

-- 2. Dim_Vessels
CREATE TABLE dim_vessels (
    vessel_id INT PRIMARY KEY,
    vessel_name VARCHAR(100) NOT NULL UNIQUE,
    type VARCHAR(50) NOT NULL
);

-- 3. Dim_Date
CREATE TABLE dim_date (
    date_key INT PRIMARY KEY,
    full_date DATE NOT NULL,
    year INT NOT NULL,
    quarter INT NOT NULL,
    month INT NOT NULL,
    month_name VARCHAR(20) NOT NULL,
    day INT NOT NULL,
    day_of_week VARCHAR(20) NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

-- 4. Dim_Weather
CREATE TABLE dim_weather (
    weather_id SERIAL PRIMARY KEY,
    weather_date DATE NOT NULL,
    port_id INT REFERENCES dim_ports(port_id),
    wind_speed_knots NUMERIC(5,2),
    sea_state_beaufort INT CHECK (sea_state_beaufort BETWEEN 0 AND 12)
);

-- 5. Fact_Shipments
CREATE TABLE fact_shipments (
    shipment_sk SERIAL PRIMARY KEY,
    shipment_id VARCHAR(30) NOT NULL,
    vessel_id INT REFERENCES dim_vessels(vessel_id),
    origin_port_id INT REFERENCES dim_ports(port_id),
    dest_port_id INT REFERENCES dim_ports(port_id),
    sched_dep_date_key INT REFERENCES dim_date(date_key),
    sched_dep_timestamp TIMESTAMP NOT NULL,
    actual_dep_timestamp TIMESTAMP,
    sched_arr_timestamp TIMESTAMP NOT NULL,
    actual_arr_timestamp TIMESTAMP,
    cargo_weight_ton NUMERIC(10,2) CHECK (cargo_weight_ton >= 0),
    fuel_consumed_liters NUMERIC(10,2),
    dep_delay_minutes NUMERIC(8,2),
    arr_delay_minutes NUMERIC(8,2),
    is_ontime_dep BOOLEAN,
    is_ontime_arr BOOLEAN
);

-- Performance Indexes
CREATE INDEX idx_fact_shipments_origin ON fact_shipments(origin_port_id);
CREATE INDEX idx_fact_shipments_dest ON fact_shipments(dest_port_id);
CREATE INDEX idx_fact_shipments_date ON fact_shipments(sched_dep_date_key);
CREATE INDEX idx_weather_date_port ON dim_weather(weather_date, port_id);