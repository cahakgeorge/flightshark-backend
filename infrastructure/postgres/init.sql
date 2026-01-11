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

-- Add compression policy (compress chunks older than 14 days)
ALTER TABLE price_history SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'origin_code, destination_code'
);

SELECT add_compression_policy('price_history', INTERVAL '14 days', if_not_exists => TRUE);

-- Add retention policy (keep 4 year of data)
SELECT add_retention_policy('price_history', INTERVAL '4 years', if_not_exists => TRUE);

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
    start_offset => INTERVAL '14 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_price_history_route 
    ON price_history (origin_code, destination_code, time DESC);

CREATE INDEX IF NOT EXISTS idx_price_history_time 
    ON price_history (time DESC);

-- =====================
-- AIRPORTS TABLE
-- =====================
CREATE TABLE IF NOT EXISTS airports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    iata_code VARCHAR(3) UNIQUE NOT NULL,
    icao_code VARCHAR(4) UNIQUE,
    name VARCHAR(255) NOT NULL,
    city VARCHAR(255) NOT NULL,
    country VARCHAR(255) NOT NULL,
    country_code VARCHAR(2) NOT NULL,
    latitude FLOAT,
    longitude FLOAT,
    timezone VARCHAR(50),
    altitude_ft INTEGER,
    airport_type VARCHAR(50) DEFAULT 'airport',
    is_active BOOLEAN DEFAULT TRUE,
    is_major BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_airports_iata ON airports(iata_code);
CREATE INDEX IF NOT EXISTS idx_airports_city ON airports(city);
CREATE INDEX IF NOT EXISTS idx_airports_country ON airports(country_code);

-- =====================
-- AIRLINES TABLE
-- =====================
CREATE TABLE IF NOT EXISTS airlines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    iata_code VARCHAR(2) UNIQUE NOT NULL,
    icao_code VARCHAR(3) UNIQUE,
    name VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    country VARCHAR(255),
    country_code VARCHAR(2),
    logo_url TEXT,
    primary_color VARCHAR(7),
    airline_type VARCHAR(50) DEFAULT 'scheduled',
    alliance VARCHAR(50),
    website VARCHAR(255),
    phone VARCHAR(50),
    hub_airports TEXT[],
    fleet_size INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    is_low_cost BOOLEAN DEFAULT FALSE,
    rating FLOAT,
    on_time_performance FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_airlines_iata ON airlines(iata_code);

-- =====================
-- CITIES TABLE
-- =====================
CREATE TABLE IF NOT EXISTS cities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    country VARCHAR(255) NOT NULL,
    country_code VARCHAR(2) NOT NULL,
    latitude FLOAT,
    longitude FLOAT,
    timezone VARCHAR(50),
    main_airport_code VARCHAR(3),
    all_airport_codes VARCHAR(50),
    population INTEGER,
    is_capital BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================
-- ROUTES TABLE
-- =====================
CREATE TABLE IF NOT EXISTS routes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    origin_code VARCHAR(3) NOT NULL,
    destination_code VARCHAR(3) NOT NULL,
    airline_code VARCHAR(2) REFERENCES airlines(iata_code),
    is_direct BOOLEAN DEFAULT TRUE,
    typical_duration_minutes INTEGER,
    distance_km INTEGER,
    flights_per_week INTEGER,
    operates_days INTEGER[],
    typical_price_low FLOAT,
    typical_price_high FLOAT,
    is_active BOOLEAN DEFAULT TRUE,
    seasonal BOOLEAN DEFAULT FALSE,
    season_start INTEGER,
    season_end INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_routes_origin ON routes(origin_code);
CREATE INDEX IF NOT EXISTS idx_routes_dest ON routes(destination_code);
CREATE INDEX IF NOT EXISTS idx_routes_pair ON routes(origin_code, destination_code);

-- =====================
-- AIRCRAFT TABLE
-- =====================
CREATE TABLE IF NOT EXISTS aircraft (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    iata_code VARCHAR(3) UNIQUE NOT NULL,
    icao_code VARCHAR(4),
    name VARCHAR(255) NOT NULL,
    manufacturer VARCHAR(100),
    model VARCHAR(100),
    typical_seats INTEGER,
    range_km INTEGER,
    cruise_speed_kmh INTEGER,
    aircraft_type VARCHAR(50) DEFAULT 'narrow_body',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =====================
-- SEED DATA: AIRLINES
-- =====================
-- Using Aviasales CDN for airline logos: https://pics.avs.io/{WIDTH}/{HEIGHT}/{IATA}.png
INSERT INTO airlines (iata_code, icao_code, name, country, country_code, is_low_cost, logo_url, alliance) VALUES
('FR', 'RYR', 'Ryanair', 'Ireland', 'IE', TRUE, 'https://pics.avs.io/100/100/FR.png', NULL),
('EI', 'EIN', 'Aer Lingus', 'Ireland', 'IE', FALSE, 'https://pics.avs.io/100/100/EI.png', NULL),
('BA', 'BAW', 'British Airways', 'United Kingdom', 'GB', FALSE, 'https://pics.avs.io/100/100/BA.png', 'Oneworld'),
('LH', 'DLH', 'Lufthansa', 'Germany', 'DE', FALSE, 'https://pics.avs.io/100/100/LH.png', 'Star Alliance'),
('AF', 'AFR', 'Air France', 'France', 'FR', FALSE, 'https://pics.avs.io/100/100/AF.png', 'SkyTeam'),
('KL', 'KLM', 'KLM', 'Netherlands', 'NL', FALSE, 'https://pics.avs.io/100/100/KL.png', 'SkyTeam'),
('IB', 'IBE', 'Iberia', 'Spain', 'ES', FALSE, 'https://pics.avs.io/100/100/IB.png', 'Oneworld'),
('VY', 'VLG', 'Vueling', 'Spain', 'ES', TRUE, 'https://pics.avs.io/100/100/VY.png', NULL),
('U2', 'EZY', 'easyJet', 'United Kingdom', 'GB', TRUE, 'https://pics.avs.io/100/100/U2.png', NULL),
('W6', 'WZZ', 'Wizz Air', 'Hungary', 'HU', TRUE, 'https://pics.avs.io/100/100/W6.png', NULL),
('SK', 'SAS', 'SAS', 'Sweden', 'SE', FALSE, 'https://pics.avs.io/100/100/SK.png', 'SkyTeam'),
('AZ', 'ITY', 'ITA Airways', 'Italy', 'IT', FALSE, 'https://pics.avs.io/100/100/AZ.png', 'SkyTeam'),
('TP', 'TAP', 'TAP Portugal', 'Portugal', 'PT', FALSE, 'https://pics.avs.io/100/100/TP.png', 'Star Alliance'),
('LX', 'SWR', 'Swiss', 'Switzerland', 'CH', FALSE, 'https://pics.avs.io/100/100/LX.png', 'Star Alliance'),
('OS', 'AUA', 'Austrian', 'Austria', 'AT', FALSE, 'https://pics.avs.io/100/100/OS.png', 'Star Alliance')
ON CONFLICT (iata_code) DO NOTHING;

-- =====================
-- SEED DATA: AIRPORTS
-- =====================
INSERT INTO airports (iata_code, icao_code, name, city, country, country_code, latitude, longitude, timezone, is_major) VALUES
-- Ireland
('DUB', 'EIDW', 'Dublin Airport', 'Dublin', 'Ireland', 'IE', 53.4213, -6.2701, 'Europe/Dublin', TRUE),
('SNN', 'EINN', 'Shannon Airport', 'Shannon', 'Ireland', 'IE', 52.7020, -8.9248, 'Europe/Dublin', FALSE),
('ORK', 'EICK', 'Cork Airport', 'Cork', 'Ireland', 'IE', 51.8413, -8.4911, 'Europe/Dublin', FALSE),
-- UK
('LHR', 'EGLL', 'Heathrow Airport', 'London', 'United Kingdom', 'GB', 51.4700, -0.4543, 'Europe/London', TRUE),
('LGW', 'EGKK', 'Gatwick Airport', 'London', 'United Kingdom', 'GB', 51.1537, -0.1821, 'Europe/London', TRUE),
('STN', 'EGSS', 'Stansted Airport', 'London', 'United Kingdom', 'GB', 51.8850, 0.2350, 'Europe/London', TRUE),
('MAN', 'EGCC', 'Manchester Airport', 'Manchester', 'United Kingdom', 'GB', 53.3537, -2.2750, 'Europe/London', TRUE),
('EDI', 'EGPH', 'Edinburgh Airport', 'Edinburgh', 'United Kingdom', 'GB', 55.9500, -3.3725, 'Europe/London', TRUE),
-- Spain
('BCN', 'LEBL', 'Barcelona El Prat', 'Barcelona', 'Spain', 'ES', 41.2971, 2.0785, 'Europe/Madrid', TRUE),
('MAD', 'LEMD', 'Madrid Barajas', 'Madrid', 'Spain', 'ES', 40.4936, -3.5668, 'Europe/Madrid', TRUE),
('AGP', 'LEMG', 'Málaga Airport', 'Málaga', 'Spain', 'ES', 36.6749, -4.4991, 'Europe/Madrid', TRUE),
('PMI', 'LEPA', 'Palma de Mallorca', 'Palma', 'Spain', 'ES', 39.5517, 2.7388, 'Europe/Madrid', TRUE),
('ALC', 'LEAL', 'Alicante Airport', 'Alicante', 'Spain', 'ES', 38.2822, -0.5582, 'Europe/Madrid', TRUE),
-- France
('CDG', 'LFPG', 'Charles de Gaulle', 'Paris', 'France', 'FR', 49.0097, 2.5479, 'Europe/Paris', TRUE),
('ORY', 'LFPO', 'Paris Orly', 'Paris', 'France', 'FR', 48.7233, 2.3794, 'Europe/Paris', TRUE),
('NCE', 'LFMN', 'Nice Côte d''Azur', 'Nice', 'France', 'FR', 43.6584, 7.2159, 'Europe/Paris', TRUE),
-- Germany
('FRA', 'EDDF', 'Frankfurt Airport', 'Frankfurt', 'Germany', 'DE', 50.0379, 8.5622, 'Europe/Berlin', TRUE),
('MUC', 'EDDM', 'Munich Airport', 'Munich', 'Germany', 'DE', 48.3538, 11.7861, 'Europe/Berlin', TRUE),
('BER', 'EDDB', 'Berlin Brandenburg', 'Berlin', 'Germany', 'DE', 52.3667, 13.5033, 'Europe/Berlin', TRUE),
-- Italy
('FCO', 'LIRF', 'Rome Fiumicino', 'Rome', 'Italy', 'IT', 41.8003, 12.2389, 'Europe/Rome', TRUE),
('MXP', 'LIMC', 'Milan Malpensa', 'Milan', 'Italy', 'IT', 45.6306, 8.7281, 'Europe/Rome', TRUE),
('VCE', 'LIPZ', 'Venice Marco Polo', 'Venice', 'Italy', 'IT', 45.5053, 12.3519, 'Europe/Rome', TRUE),
-- Netherlands
('AMS', 'EHAM', 'Amsterdam Schiphol', 'Amsterdam', 'Netherlands', 'NL', 52.3086, 4.7639, 'Europe/Amsterdam', TRUE),
-- Portugal
('LIS', 'LPPT', 'Lisbon Portela', 'Lisbon', 'Portugal', 'PT', 38.7813, -9.1359, 'Europe/Lisbon', TRUE),
('OPO', 'LPPR', 'Porto Airport', 'Porto', 'Portugal', 'PT', 41.2481, -8.6814, 'Europe/Lisbon', TRUE),
('FAO', 'LPFR', 'Faro Airport', 'Faro', 'Portugal', 'PT', 37.0144, -7.9659, 'Europe/Lisbon', TRUE),
-- Other
('CPH', 'EKCH', 'Copenhagen Airport', 'Copenhagen', 'Denmark', 'DK', 55.6180, 12.6560, 'Europe/Copenhagen', TRUE),
('VIE', 'LOWW', 'Vienna Airport', 'Vienna', 'Austria', 'AT', 48.1103, 16.5697, 'Europe/Vienna', TRUE),
('ZRH', 'LSZH', 'Zurich Airport', 'Zurich', 'Switzerland', 'CH', 47.4647, 8.5492, 'Europe/Zurich', TRUE),
('BRU', 'EBBR', 'Brussels Airport', 'Brussels', 'Belgium', 'BE', 50.9014, 4.4844, 'Europe/Brussels', TRUE)
ON CONFLICT (iata_code) DO NOTHING;

-- =====================
-- SEED DATA: ROUTES
-- =====================
INSERT INTO routes (origin_code, destination_code, airline_code, typical_duration_minutes, distance_km, typical_price_low, typical_price_high) VALUES
('DUB', 'BCN', 'FR', 150, 1475, 30, 150),
('DUB', 'BCN', 'EI', 155, 1475, 80, 250),
('DUB', 'MAD', 'FR', 145, 1450, 35, 140),
('DUB', 'MAD', 'IB', 150, 1450, 90, 280),
('DUB', 'LHR', 'EI', 75, 464, 50, 200),
('DUB', 'LHR', 'BA', 75, 464, 60, 250),
('DUB', 'CDG', 'EI', 95, 787, 60, 180),
('DUB', 'CDG', 'AF', 95, 787, 80, 220),
('DUB', 'AMS', 'EI', 100, 755, 55, 170),
('DUB', 'AMS', 'KL', 100, 755, 70, 200),
('LHR', 'BCN', 'BA', 130, 1138, 60, 220),
('LHR', 'BCN', 'VY', 130, 1138, 40, 150),
('LHR', 'MAD', 'BA', 140, 1261, 70, 250),
('LHR', 'MAD', 'IB', 140, 1261, 65, 240)
ON CONFLICT DO NOTHING;

-- =====================
-- SEED DATA: AIRCRAFT
-- =====================
INSERT INTO aircraft (iata_code, icao_code, name, manufacturer, model, typical_seats, aircraft_type) VALUES
('738', 'B738', 'Boeing 737-800', 'Boeing', '737-800', 189, 'narrow_body'),
('73H', 'B738', 'Boeing 737-800 (Winglets)', 'Boeing', '737-800', 189, 'narrow_body'),
('320', 'A320', 'Airbus A320', 'Airbus', 'A320', 180, 'narrow_body'),
('321', 'A321', 'Airbus A321', 'Airbus', 'A321', 220, 'narrow_body'),
('319', 'A319', 'Airbus A319', 'Airbus', 'A319', 156, 'narrow_body'),
('32N', 'A20N', 'Airbus A320neo', 'Airbus', 'A320neo', 180, 'narrow_body'),
('77W', 'B77W', 'Boeing 777-300ER', 'Boeing', '777-300ER', 396, 'wide_body'),
('788', 'B788', 'Boeing 787-8 Dreamliner', 'Boeing', '787-8', 242, 'wide_body'),
('789', 'B789', 'Boeing 787-9 Dreamliner', 'Boeing', '787-9', 290, 'wide_body'),
('359', 'A359', 'Airbus A350-900', 'Airbus', 'A350-900', 325, 'wide_body'),
('E90', 'E190', 'Embraer E190', 'Embraer', 'E190', 100, 'regional')
ON CONFLICT (iata_code) DO NOTHING;

-- =====================
-- SEED: PRICE HISTORY
-- =====================
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
    RAISE NOTICE 'Seeded: airports, airlines, routes, aircraft, price_history';
END $$;

