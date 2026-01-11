-- Enhanced Reference Data Schema
-- Run with: docker compose exec postgres psql -U flightshark -d flightshark -f /migrations/001_enhanced_reference_data.sql

-- =====================
-- AIRPORT DESTINATIONS (Denormalized)
-- Which destinations can you fly to from each airport
-- =====================
CREATE TABLE IF NOT EXISTS airport_destinations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    airport_code VARCHAR(3) NOT NULL REFERENCES airports(iata_code),
    destination_code VARCHAR(3) NOT NULL,
    destination_city VARCHAR(255),
    destination_country VARCHAR(255),
    destination_country_code VARCHAR(2),
    
    -- Airlines serving this route (denormalized array)
    airlines_serving TEXT[],
    airline_count INTEGER DEFAULT 0,
    
    -- Flight frequency
    daily_flights INTEGER,
    weekly_flights INTEGER,
    
    -- Price ranges (updated periodically)
    price_low DECIMAL(10,2),
    price_high DECIMAL(10,2),
    price_avg DECIMAL(10,2),
    price_currency VARCHAR(3) DEFAULT 'EUR',
    price_updated_at TIMESTAMPTZ,
    
    -- Flight details
    flight_duration_minutes INTEGER,
    distance_km INTEGER,
    is_direct BOOLEAN DEFAULT TRUE,
    
    -- Metadata
    is_seasonal BOOLEAN DEFAULT FALSE,
    season_months INTEGER[],  -- e.g., {6,7,8} for summer
    is_active BOOLEAN DEFAULT TRUE,
    popularity_score INTEGER DEFAULT 0,  -- Based on search volume
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(airport_code, destination_code)
);

CREATE INDEX IF NOT EXISTS idx_airport_dest_origin ON airport_destinations(airport_code);
CREATE INDEX IF NOT EXISTS idx_airport_dest_dest ON airport_destinations(destination_code);
CREATE INDEX IF NOT EXISTS idx_airport_dest_active ON airport_destinations(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_airport_dest_popularity ON airport_destinations(airport_code, popularity_score DESC);

-- =====================
-- AIRLINE ROUTES (Denormalized)
-- All routes operated by each airline
-- =====================
CREATE TABLE IF NOT EXISTS airline_routes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    airline_code VARCHAR(2) NOT NULL REFERENCES airlines(iata_code),
    origin_code VARCHAR(3) NOT NULL,
    destination_code VARCHAR(3) NOT NULL,
    
    -- Route details
    origin_city VARCHAR(255),
    origin_country VARCHAR(255),
    destination_city VARCHAR(255),
    destination_country VARCHAR(255),
    
    -- Flight frequency
    daily_flights INTEGER,
    weekly_flights INTEGER,
    flights_per_month INTEGER,
    
    -- Equipment
    aircraft_types TEXT[],  -- e.g., {'738', '320'}
    
    -- Pricing
    price_low DECIMAL(10,2),
    price_high DECIMAL(10,2),
    price_avg DECIMAL(10,2),
    price_currency VARCHAR(3) DEFAULT 'EUR',
    
    -- Flight times
    duration_minutes INTEGER,
    distance_km INTEGER,
    
    -- Schedule
    is_direct BOOLEAN DEFAULT TRUE,
    operates_days INTEGER[],  -- 1=Mon, 7=Sun
    first_departure TIME,
    last_departure TIME,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_seasonal BOOLEAN DEFAULT FALSE,
    season_start DATE,
    season_end DATE,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(airline_code, origin_code, destination_code)
);

CREATE INDEX IF NOT EXISTS idx_airline_routes_airline ON airline_routes(airline_code);
CREATE INDEX IF NOT EXISTS idx_airline_routes_origin ON airline_routes(origin_code);
CREATE INDEX IF NOT EXISTS idx_airline_routes_dest ON airline_routes(destination_code);
CREATE INDEX IF NOT EXISTS idx_airline_routes_pair ON airline_routes(origin_code, destination_code);

-- =====================
-- POPULAR ROUTES (Cached)
-- Frequently searched routes with aggregated data
-- =====================
CREATE TABLE IF NOT EXISTS popular_routes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    origin_code VARCHAR(3) NOT NULL,
    destination_code VARCHAR(3) NOT NULL,
    
    -- Aggregated info
    origin_city VARCHAR(255),
    origin_country VARCHAR(255),
    destination_city VARCHAR(255),
    destination_country VARCHAR(255),
    
    -- All airlines on this route (denormalized)
    airlines JSONB,  -- [{code: 'FR', name: 'Ryanair', price_avg: 49}, ...]
    airline_count INTEGER DEFAULT 0,
    
    -- Price summary
    cheapest_airline VARCHAR(2),
    cheapest_price DECIMAL(10,2),
    price_range_low DECIMAL(10,2),
    price_range_high DECIMAL(10,2),
    avg_price DECIMAL(10,2),
    price_currency VARCHAR(3) DEFAULT 'EUR',
    price_trend VARCHAR(20),  -- 'rising', 'falling', 'stable'
    
    -- Flight frequency (all airlines combined)
    total_daily_flights INTEGER,
    total_weekly_flights INTEGER,
    has_direct_flights BOOLEAN DEFAULT TRUE,
    
    -- Duration
    min_duration_minutes INTEGER,
    max_duration_minutes INTEGER,
    avg_duration_minutes INTEGER,
    distance_km INTEGER,
    
    -- Popularity metrics
    search_count_7d INTEGER DEFAULT 0,
    search_count_30d INTEGER DEFAULT 0,
    booking_conversion_rate FLOAT,
    popularity_rank INTEGER,
    
    -- Best times
    best_departure_days INTEGER[],  -- Best days to depart
    cheapest_months INTEGER[],       -- Cheapest months to fly
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    data_quality_score FLOAT,  -- How complete/fresh the data is
    
    last_price_check TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(origin_code, destination_code)
);

CREATE INDEX IF NOT EXISTS idx_popular_routes_origin ON popular_routes(origin_code);
CREATE INDEX IF NOT EXISTS idx_popular_routes_dest ON popular_routes(destination_code);
CREATE INDEX IF NOT EXISTS idx_popular_routes_popularity ON popular_routes(popularity_rank);
CREATE INDEX IF NOT EXISTS idx_popular_routes_cheapest ON popular_routes(cheapest_price);

-- =====================
-- AIRPORT STATS (Denormalized)
-- Pre-computed statistics for each airport
-- =====================
CREATE TABLE IF NOT EXISTS airport_stats (
    airport_code VARCHAR(3) PRIMARY KEY REFERENCES airports(iata_code),
    
    -- Destination counts
    direct_destinations_count INTEGER DEFAULT 0,
    total_destinations_count INTEGER DEFAULT 0,
    countries_served INTEGER DEFAULT 0,
    
    -- Airline presence
    airlines_serving TEXT[],
    airline_count INTEGER DEFAULT 0,
    low_cost_airlines TEXT[],
    legacy_airlines TEXT[],
    
    -- Top destinations (cached)
    top_destinations JSONB,  -- [{code: 'BCN', city: 'Barcelona', flights_weekly: 56}, ...]
    top_countries JSONB,     -- [{code: 'ES', name: 'Spain', routes: 12}, ...]
    
    -- Route summary
    busiest_route VARCHAR(7),  -- e.g., 'DUB-LHR'
    busiest_route_flights INTEGER,
    
    -- Price stats
    avg_price_domestic DECIMAL(10,2),
    avg_price_european DECIMAL(10,2),
    avg_price_long_haul DECIMAL(10,2),
    cheapest_destination VARCHAR(3),
    cheapest_price DECIMAL(10,2),
    
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================
-- DATA SYNC LOG
-- Track when data was last fetched from each source
-- =====================
CREATE TABLE IF NOT EXISTS data_sync_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    data_type VARCHAR(50) NOT NULL,  -- 'airports', 'airlines', 'routes', etc.
    source VARCHAR(50) NOT NULL,      -- 'amadeus', 'ourairports', etc.
    status VARCHAR(20) NOT NULL,      -- 'success', 'failed', 'partial'
    records_fetched INTEGER DEFAULT 0,
    records_created INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_seconds FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sync_log_type ON data_sync_log(data_type, created_at DESC);

-- =====================
-- HELPER FUNCTION: Update timestamp trigger
-- =====================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers
DROP TRIGGER IF EXISTS update_airport_destinations_timestamp ON airport_destinations;
CREATE TRIGGER update_airport_destinations_timestamp
    BEFORE UPDATE ON airport_destinations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_airline_routes_timestamp ON airline_routes;
CREATE TRIGGER update_airline_routes_timestamp
    BEFORE UPDATE ON airline_routes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_popular_routes_timestamp ON popular_routes;
CREATE TRIGGER update_popular_routes_timestamp
    BEFORE UPDATE ON popular_routes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
