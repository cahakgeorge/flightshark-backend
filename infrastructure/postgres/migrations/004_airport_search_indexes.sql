-- Add indexes for faster airport search
-- These indexes dramatically improve ILIKE query performance

-- Index on city column for prefix search (city ILIKE 'query%')
CREATE INDEX IF NOT EXISTS idx_airports_city_lower 
ON airports (LOWER(city) varchar_pattern_ops);

-- Index on name column for prefix search
CREATE INDEX IF NOT EXISTS idx_airports_name_lower 
ON airports (LOWER(name) varchar_pattern_ops);

-- Composite index for active airports (most common filter)
CREATE INDEX IF NOT EXISTS idx_airports_active_major 
ON airports (is_active, is_major DESC, city);

-- If pg_trgm extension is available, add trigram indexes for fuzzy matching
-- This allows fast %query% searches
DO $$
BEGIN
    -- Check if pg_trgm extension exists, if not create it
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    
    -- GIN index for trigram matching on city
    CREATE INDEX IF NOT EXISTS idx_airports_city_trgm 
    ON airports USING GIN (city gin_trgm_ops);
    
    -- GIN index for trigram matching on name
    CREATE INDEX IF NOT EXISTS idx_airports_name_trgm 
    ON airports USING GIN (name gin_trgm_ops);
    
    RAISE NOTICE 'Trigram indexes created successfully';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Could not create trigram indexes: %', SQLERRM;
END $$;

-- Analyze the table to update statistics
ANALYZE airports;
