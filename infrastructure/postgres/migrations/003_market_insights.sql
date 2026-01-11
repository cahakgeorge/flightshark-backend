-- Migration: Market Insights Tables
-- For storing Amadeus Market Insights API data
-- Version: 003

-- ========================================
-- Most Traveled Destinations
-- ========================================
CREATE TABLE IF NOT EXISTS traveled_destinations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Origin
    origin_code VARCHAR(3) NOT NULL,
    
    -- Destination
    destination_code VARCHAR(3) NOT NULL,
    destination_city VARCHAR(255),
    destination_country VARCHAR(255),
    destination_country_code VARCHAR(2),
    
    -- Metrics
    travelers_count INTEGER,
    flights_count INTEGER,
    analytics_score FLOAT,
    
    -- Ranking
    rank INTEGER,
    
    -- Period
    period_type VARCHAR(20) DEFAULT 'YEARLY',
    period_year INTEGER,
    period_month INTEGER,
    period_quarter INTEGER,
    
    -- Metadata
    raw_data JSONB,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_traveled_dest_origin ON traveled_destinations(origin_code);
CREATE INDEX IF NOT EXISTS ix_traveled_dest_origin_rank ON traveled_destinations(origin_code, rank);

-- Unique constraint for upsert
ALTER TABLE traveled_destinations 
ADD CONSTRAINT IF NOT EXISTS uq_traveled_dest_period 
UNIQUE (origin_code, destination_code, period_type, period_year, period_month);


-- ========================================
-- Most Booked Destinations
-- ========================================
CREATE TABLE IF NOT EXISTS booked_destinations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Origin
    origin_code VARCHAR(3) NOT NULL,
    
    -- Destination
    destination_code VARCHAR(3) NOT NULL,
    destination_city VARCHAR(255),
    destination_country VARCHAR(255),
    destination_country_code VARCHAR(2),
    
    -- Metrics
    bookings_count INTEGER,
    analytics_score FLOAT,
    
    -- Ranking
    rank INTEGER,
    
    -- Period
    period_type VARCHAR(20) DEFAULT 'YEARLY',
    period_year INTEGER,
    period_month INTEGER,
    period_quarter INTEGER,
    
    -- Metadata
    raw_data JSONB,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_booked_dest_origin ON booked_destinations(origin_code);
CREATE INDEX IF NOT EXISTS ix_booked_dest_origin_rank ON booked_destinations(origin_code, rank);

-- Unique constraint
ALTER TABLE booked_destinations 
ADD CONSTRAINT IF NOT EXISTS uq_booked_dest_period 
UNIQUE (origin_code, destination_code, period_type, period_year, period_month);


-- ========================================
-- Busiest Travel Periods
-- ========================================
CREATE TABLE IF NOT EXISTS busiest_travel_periods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Location
    origin_code VARCHAR(3) NOT NULL,
    destination_code VARCHAR(3),
    
    -- Period
    period_month INTEGER NOT NULL,
    period_year INTEGER NOT NULL,
    
    -- Metrics
    travelers_count INTEGER,
    flights_count INTEGER,
    analytics_score FLOAT,
    
    -- Direction
    direction VARCHAR(20) DEFAULT 'DEPARTING',
    
    -- Ranking
    rank INTEGER,
    
    -- Metadata
    raw_data JSONB,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_busiest_origin ON busiest_travel_periods(origin_code);
CREATE INDEX IF NOT EXISTS ix_busiest_origin_direction ON busiest_travel_periods(origin_code, direction);

-- Unique constraint
ALTER TABLE busiest_travel_periods 
ADD CONSTRAINT IF NOT EXISTS uq_busiest_period 
UNIQUE (origin_code, destination_code, period_year, period_month, direction);


-- ========================================
-- Trending Destinations (Aggregated)
-- ========================================
CREATE TABLE IF NOT EXISTS trending_destinations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Origin (GLOBAL for worldwide aggregation)
    origin_code VARCHAR(10) NOT NULL,
    
    -- Destination
    destination_code VARCHAR(3) NOT NULL,
    destination_city VARCHAR(255),
    destination_country VARCHAR(255),
    destination_country_code VARCHAR(2),
    
    -- Scores
    trending_score FLOAT DEFAULT 0,
    travel_score FLOAT DEFAULT 0,
    booking_score FLOAT DEFAULT 0,
    search_score FLOAT DEFAULT 0,
    social_score FLOAT DEFAULT 0,
    
    -- Trend
    score_change FLOAT DEFAULT 0,
    
    -- Ranking
    rank INTEGER,
    
    -- Extra
    image_url VARCHAR(500),
    tags JSONB DEFAULT '[]',
    
    -- Metadata
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    valid_until TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_trending_origin ON trending_destinations(origin_code);
CREATE INDEX IF NOT EXISTS ix_trending_rank ON trending_destinations(origin_code, rank);
CREATE INDEX IF NOT EXISTS ix_trending_score ON trending_destinations(origin_code, trending_score DESC);

-- Unique constraint
ALTER TABLE trending_destinations 
ADD CONSTRAINT IF NOT EXISTS uq_trending_dest 
UNIQUE (origin_code, destination_code);


-- ========================================
-- Sync Log
-- ========================================
CREATE TABLE IF NOT EXISTS market_insights_sync_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    sync_type VARCHAR(50) NOT NULL,
    origin_code VARCHAR(10),
    
    status VARCHAR(20) NOT NULL,
    
    records_fetched INTEGER DEFAULT 0,
    records_created INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    
    error_message VARCHAR(1000),
    
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_seconds FLOAT,
    
    metadata JSONB
);

-- Index for querying recent syncs
CREATE INDEX IF NOT EXISTS ix_sync_log_type_time ON market_insights_sync_log(sync_type, started_at DESC);


-- ========================================
-- Create update trigger for updated_at
-- ========================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to tables
DROP TRIGGER IF EXISTS update_traveled_destinations_updated_at ON traveled_destinations;
CREATE TRIGGER update_traveled_destinations_updated_at
    BEFORE UPDATE ON traveled_destinations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_booked_destinations_updated_at ON booked_destinations;
CREATE TRIGGER update_booked_destinations_updated_at
    BEFORE UPDATE ON booked_destinations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_busiest_travel_periods_updated_at ON busiest_travel_periods;
CREATE TRIGGER update_busiest_travel_periods_updated_at
    BEFORE UPDATE ON busiest_travel_periods
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_trending_destinations_updated_at ON trending_destinations;
CREATE TRIGGER update_trending_destinations_updated_at
    BEFORE UPDATE ON trending_destinations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- Log migration
INSERT INTO data_sync_log (data_type, source, status, completed_at, metadata)
VALUES ('MIGRATION', '003_market_insights', 'SUCCESS', NOW(), '{"version": "003", "description": "Market Insights tables"}'::jsonb)
ON CONFLICT DO NOTHING;

-- Done
SELECT 'Market Insights migration complete' AS status;
