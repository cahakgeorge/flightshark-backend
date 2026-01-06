-- Flightshark Database Initialization
-- This script runs when the PostgreSQL container is first created

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- TimescaleDB should already be enabled in the base image
-- But let's make sure
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Create price_history hypertable for time-series data
CREATE TABLE IF NOT EXISTS price_history (
    time TIMESTAMPTZ NOT NULL,
    origin_code VARCHAR(10) NOT NULL,
    destination_code VARCHAR(10) NOT NULL,
    airline VARCHAR(100),
    price DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'EUR',
    cabin_class VARCHAR(50) DEFAULT 'economy',
    source VARCHAR(50),
    PRIMARY KEY (time, origin_code, destination_code, airline)
);

-- Convert to hypertable (TimescaleDB)
SELECT create_hypertable('price_history', 'time', if_not_exists => TRUE);

-- Add compression policy (compress chunks older than 7 days)
ALTER TABLE price_history SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'origin_code, destination_code'
);

SELECT add_compression_policy('price_history', INTERVAL '7 days', if_not_exists => TRUE);

-- Add retention policy (keep 1 year of data)
SELECT add_retention_policy('price_history', INTERVAL '1 year', if_not_exists => TRUE);

-- Create continuous aggregate for daily price averages
CREATE MATERIALIZED VIEW IF NOT EXISTS price_daily_avg
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', time) AS day,
    origin_code,
    destination_code,
    AVG(price) as avg_price,
    MIN(price) as min_price,
    MAX(price) as max_price,
    COUNT(*) as sample_count
FROM price_history
GROUP BY day, origin_code, destination_code
WITH NO DATA;

-- Refresh policy for the continuous aggregate
SELECT add_continuous_aggregate_policy('price_daily_avg',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_price_history_route 
    ON price_history (origin_code, destination_code, time DESC);

CREATE INDEX IF NOT EXISTS idx_price_history_time 
    ON price_history (time DESC);

-- Insert some sample price data for testing
INSERT INTO price_history (time, origin_code, destination_code, airline, price, source)
SELECT 
    NOW() - (interval '1 day' * generate_series(1, 30)),
    'DUB',
    'BCN',
    (ARRAY['Ryanair', 'Aer Lingus', 'Vueling'])[floor(random() * 3 + 1)],
    50 + random() * 150,
    'mock'
FROM generate_series(1, 30)
ON CONFLICT DO NOTHING;

-- Log completion
DO $$
BEGIN
    RAISE NOTICE 'Flightshark database initialization complete!';
END $$;

