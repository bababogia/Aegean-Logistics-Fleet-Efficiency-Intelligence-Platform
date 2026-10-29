-- =============================================================================
-- Query 1: On-Time Departure & Arrival Performance Matrix per Port
-- Calculates On-Time rates and ranks ports by overall reliability.
-- =============================================================================
WITH PortDepartureStats AS (
    SELECT 
        p.port_name,
        COUNT(f.shipment_sk) AS total_departures,
        COUNT(CASE WHEN f.is_ontime_dep = TRUE THEN 1 END) AS ontime_departures,
        AVG(GREATEST(f.dep_delay_minutes, 0)) AS avg_dep_delay_mins
    FROM fact_shipments f
    JOIN dim_ports p ON f.origin_port_id = p.port_id
    GROUP BY p.port_name
),
PortArrivalStats AS (
    SELECT 
        p.port_name,
        COUNT(f.shipment_sk) AS total_arrivals,
        COUNT(CASE WHEN f.is_ontime_arr = TRUE THEN 1 END) AS ontime_arrivals,
        AVG(GREATEST(f.arr_delay_minutes, 0)) AS avg_arr_delay_mins
    FROM fact_shipments f
    JOIN dim_ports p ON f.dest_port_id = p.port_id
    WHERE f.actual_arr_timestamp IS NOT NULL
    GROUP BY p.port_name
)
SELECT 
    d.port_name,
    d.total_departures,
    ROUND((d.ontime_departures::NUMERIC / d.total_departures) * 100, 2) AS ontime_dep_pct,
    ROUND(d.avg_dep_delay_mins, 1) AS avg_dep_delay_mins,
    a.total_arrivals,
    ROUND((a.ontime_arrivals::NUMERIC / a.total_arrivals) * 100, 2) AS ontime_arr_pct,
    ROUND(a.avg_arr_delay_mins, 1) AS avg_arr_delay_mins,
    DENSE_RANK() OVER (
        ORDER BY ((d.ontime_departures::NUMERIC / d.total_departures) + (a.ontime_arrivals::NUMERIC / a.total_arrivals)) / 2 DESC
    ) AS port_reliability_rank
FROM PortDepartureStats d
JOIN PortArrivalStats a ON d.port_name = a.port_name
ORDER BY port_reliability_rank;


-- =============================================================================
-- Query 2: Fuel Consumption Variance Analysis Across Weather Conditions
-- Benchmarks actual fuel consumption against expected baselines under Beaufort scale levels.
-- =============================================================================
WITH ShipmentWeatherImpact AS (
    SELECT 
        f.shipment_id,
        v.vessel_name,
        w.sea_state_beaufort,
        f.cargo_weight_ton,
        f.fuel_consumed_liters AS actual_fuel,
        -- Baseline fuel expected formula under calm sea state (Beaufort <= 3)
        AVG(f.fuel_consumed_liters) OVER (
            PARTITION BY f.vessel_id, f.origin_port_id, f.dest_port_id
        ) AS expected_baseline_fuel
    FROM fact_shipments f
    JOIN dim_vessels v ON f.vessel_id = v.vessel_id
    JOIN dim_weather w ON f.origin_port_id = w.port_id 
                      AND CAST(f.sched_dep_timestamp AS DATE) = w.weather_date
    WHERE f.fuel_consumed_liters IS NOT NULL
),
FuelVarianceSummary AS (
    SELECT 
        sea_state_beaufort,
        COUNT(shipment_id) AS trip_count,
        ROUND(AVG(actual_fuel), 2) AS avg_actual_fuel_liters,
        ROUND(AVG(expected_baseline_fuel), 2) AS avg_expected_fuel_liters,
        ROUND(AVG(actual_fuel - expected_baseline_fuel), 2) AS avg_fuel_variance_liters,
        ROUND(
            (AVG(actual_fuel - expected_baseline_fuel) / NULLIF(AVG(expected_baseline_fuel), 0)) * 100, 2
        ) AS pct_fuel_inefficiency
    FROM ShipmentWeatherImpact
    GROUP BY sea_state_beaufort
)
SELECT 
    sea_state_beaufort,
    trip_count,
    avg_actual_fuel_liters,
    avg_expected_fuel_liters,
    avg_fuel_variance_liters,
    pct_fuel_inefficiency,
    AVG(pct_fuel_inefficiency) OVER () AS fleet_avg_fuel_variance_pct
FROM FuelVarianceSummary
ORDER BY sea_state_beaufort ASC;


-- =============================================================================
-- Query 3: Month-over-Month (MoM) Cargo Tonnage Trends per Shipping Lane
-- Evaluates route volume fluctuations using LAG window functions.
-- =============================================================================
WITH MonthlyLaneMetrics AS (
    SELECT 
        orig.port_name || ' -> ' || dest.port_name AS shipping_lane,
        d.year,
        d.month,
        d.month_name,
        COUNT(f.shipment_sk) AS total_shipments,
        SUM(f.cargo_weight_ton) AS total_cargo_tons
    FROM fact_shipments f
    JOIN dim_ports orig ON f.origin_port_id = orig.port_id
    JOIN dim_ports dest ON f.dest_port_id = dest.port_id
    JOIN dim_date d ON f.sched_dep_date_key = d.date_key
    GROUP BY orig.port_name, dest.port_name, d.year, d.month, d.month_name
),
MoMLaneAnalysis AS (
    SELECT 
        shipping_lane,
        year,
        month,
        month_name,
        total_shipments,
        total_cargo_tons,
        LAG(total_cargo_tons, 1) OVER (
            PARTITION BY shipping_lane ORDER BY year, month
        ) AS prev_month_cargo_tons
    FROM MonthlyLaneMetrics
)
SELECT 
    shipping_lane,
    year,
    month_name,
    total_shipments,
    ROUND(total_cargo_tons, 2) AS current_month_tons,
    ROUND(prev_month_cargo_tons, 2) AS prior_month_tons,
    ROUND(
        COALESCE(
            ((total_cargo_tons - prev_month_cargo_tons) / NULLIF(prev_month_cargo_tons, 0)) * 100, 
            0
        ), 2
    ) AS mom_volume_growth_pct
FROM MoMLaneAnalysis
ORDER BY shipping_lane, year, month;