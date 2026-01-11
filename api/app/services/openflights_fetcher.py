"""
OpenFlights Data Fetcher
Fetches free/open airport, airline, and route data from OpenFlights.org
This is useful for bulk seeding without API rate limits
"""
import httpx
import csv
import io
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


class OpenFlightsDataFetcher:
    """
    Fetches data from OpenFlights.org public datasets
    https://openflights.org/data.html
    """
    
    AIRPORTS_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
    AIRLINES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
    ROUTES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"
    COUNTRIES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/countries.dat"
    
    # Common country name to ISO code mapping (for countries not in the countries.dat file)
    COUNTRY_CODE_MAP = {
        "United States": "US", "United Kingdom": "GB", "Germany": "DE", "France": "FR",
        "Spain": "ES", "Italy": "IT", "Netherlands": "NL", "Belgium": "BE", "Austria": "AT",
        "Switzerland": "CH", "Portugal": "PT", "Ireland": "IE", "Sweden": "SE", "Norway": "NO",
        "Denmark": "DK", "Finland": "FI", "Poland": "PL", "Czech Republic": "CZ", "Greece": "GR",
        "Turkey": "TR", "Russia": "RU", "Ukraine": "UA", "Hungary": "HU", "Romania": "RO",
        "Bulgaria": "BG", "Croatia": "HR", "Slovenia": "SI", "Slovakia": "SK", "Serbia": "RS",
        "Canada": "CA", "Mexico": "MX", "Brazil": "BR", "Argentina": "AR", "Chile": "CL",
        "Colombia": "CO", "Peru": "PE", "Australia": "AU", "New Zealand": "NZ", "Japan": "JP",
        "China": "CN", "South Korea": "KR", "India": "IN", "Thailand": "TH", "Singapore": "SG",
        "Malaysia": "MY", "Indonesia": "ID", "Philippines": "PH", "Vietnam": "VN", "Taiwan": "TW",
        "Hong Kong": "HK", "United Arab Emirates": "AE", "Saudi Arabia": "SA", "Israel": "IL",
        "Egypt": "EG", "South Africa": "ZA", "Morocco": "MA", "Kenya": "KE", "Nigeria": "NG",
        "Iceland": "IS", "Luxembourg": "LU", "Malta": "MT", "Cyprus": "CY", "Estonia": "EE",
        "Latvia": "LV", "Lithuania": "LT", "Moldova": "MD", "Belarus": "BY", "Georgia": "GE",
        "Armenia": "AM", "Azerbaijan": "AZ", "Kazakhstan": "KZ", "Uzbekistan": "UZ",
        "Pakistan": "PK", "Bangladesh": "BD", "Sri Lanka": "LK", "Nepal": "NP", "Myanmar": "MM",
        "Cambodia": "KH", "Laos": "LA", "Brunei": "BN", "Mongolia": "MN", "North Korea": "KP",
        "Papua New Guinea": "PG", "Fiji": "FJ", "New Caledonia": "NC", "Greenland": "GL",
        "Puerto Rico": "PR", "Cuba": "CU", "Jamaica": "JM", "Dominican Republic": "DO",
        "Bahamas": "BS", "Trinidad and Tobago": "TT", "Barbados": "BB", "Panama": "PA",
        "Costa Rica": "CR", "Guatemala": "GT", "Honduras": "HN", "El Salvador": "SV",
        "Nicaragua": "NI", "Ecuador": "EC", "Venezuela": "VE", "Bolivia": "BO", "Paraguay": "PY",
        "Uruguay": "UY", "Guyana": "GY", "Suriname": "SR", "French Guiana": "GF",
        "Qatar": "QA", "Kuwait": "KW", "Bahrain": "BH", "Oman": "OM", "Jordan": "JO",
        "Lebanon": "LB", "Iraq": "IQ", "Iran": "IR", "Afghanistan": "AF", "Syria": "SY",
        "Yemen": "YE", "Tunisia": "TN", "Algeria": "DZ", "Libya": "LY", "Sudan": "SD",
        "Ethiopia": "ET", "Tanzania": "TZ", "Uganda": "UG", "Rwanda": "RW", "Zambia": "ZM",
        "Zimbabwe": "ZW", "Botswana": "BW", "Namibia": "NA", "Mozambique": "MZ", "Angola": "AO",
        "Ghana": "GH", "Ivory Coast": "CI", "Senegal": "SN", "Cameroon": "CM", "Gabon": "GA",
        "Mauritius": "MU", "Madagascar": "MG", "Reunion": "RE", "Seychelles": "SC",
        "Maldives": "MV", "Montenegro": "ME", "Kosovo": "XK", "North Macedonia": "MK",
        "Bosnia and Herzegovina": "BA", "Albania": "AL", "Andorra": "AD", "Monaco": "MC",
        "San Marino": "SM", "Vatican City": "VA", "Liechtenstein": "LI", "Faroe Islands": "FO",
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.country_codes: Dict[str, str] = dict(self.COUNTRY_CODE_MAP)
    
    async def _load_country_codes(self):
        """Load country codes from OpenFlights countries.dat"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.COUNTRIES_URL)
                response.raise_for_status()
            
            # Format: name, iso_code, dafif_code
            reader = csv.reader(io.StringIO(response.text))
            for row in reader:
                if len(row) >= 2:
                    name, iso_code = row[0], row[1]
                    if name and iso_code:
                        self.country_codes[name] = iso_code
            
            logger.info(f"Loaded {len(self.country_codes)} country codes")
        except Exception as e:
            logger.warning(f"Could not load country codes from OpenFlights: {e}")
    
    def _get_country_code(self, country_name: str) -> str:
        """Get ISO country code from country name"""
        if not country_name:
            return ""
        return self.country_codes.get(country_name, "")
    
    async def fetch_and_seed_airports(self) -> Dict[str, int]:
        """
        Fetch airports from OpenFlights and seed to database
        Returns stats: {fetched, created, updated}
        """
        logger.info("Fetching airports from OpenFlights...")
        
        # Load country codes first
        await self._load_country_codes()
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(self.AIRPORTS_URL)
            response.raise_for_status()
        
        # OpenFlights airports.dat format:
        # Airport ID, Name, City, Country, IATA, ICAO, Lat, Lon, Alt, Timezone, DST, Tz database, Type, Source
        reader = csv.reader(io.StringIO(response.text))
        
        stats = {"fetched": 0, "created": 0, "updated": 0, "skipped": 0}
        
        for row in reader:
            try:
                if len(row) < 12:
                    continue
                    
                airport_id, name, city, country, iata, icao, lat, lon, alt, tz_offset, dst, tz_db = row[:12]
                
                # Skip airports without IATA codes or invalid codes
                if not iata or iata == "\\N" or len(iata) != 3:
                    continue
                
                stats["fetched"] += 1
                
                # Determine if major airport (rough heuristic based on name)
                is_major = any(keyword in name.lower() for keyword in [
                    "international", "intl", "main", "primary", "central"
                ])
                
                # Get country code from mapping
                country_code = self._get_country_code(country)
                
                # Insert/update airport - skip ICAO to avoid unique conflicts
                # Some airports share ICAO or have NULL ICAO
                result = await self.db.execute(text("""
                    INSERT INTO airports (
                        iata_code, name, city, country,
                        country_code, latitude, longitude, altitude_ft,
                        timezone, is_major
                    ) VALUES (
                        :iata, :name, :city, :country,
                        :country_code, :lat, :lon, :alt, :tz, :is_major
                    )
                    ON CONFLICT (iata_code) DO UPDATE SET
                        name = COALESCE(EXCLUDED.name, airports.name),
                        city = COALESCE(EXCLUDED.city, airports.city),
                        country = COALESCE(EXCLUDED.country, airports.country),
                        country_code = COALESCE(NULLIF(EXCLUDED.country_code, ''), airports.country_code),
                        latitude = COALESCE(EXCLUDED.latitude, airports.latitude),
                        longitude = COALESCE(EXCLUDED.longitude, airports.longitude),
                        updated_at = NOW()
                    RETURNING (xmax = 0) AS is_insert
                """), {
                    "iata": iata,
                    "name": name,
                    "city": city,
                    "country": country,
                    "country_code": country_code,
                    "lat": float(lat) if lat and lat != "\\N" else None,
                    "lon": float(lon) if lon and lon != "\\N" else None,
                    "alt": int(float(alt)) if alt and alt != "\\N" else None,
                    "tz": tz_db if tz_db and tz_db != "\\N" else None,
                    "is_major": is_major
                })
                
                row_result = result.fetchone()
                if row_result and row_result[0]:
                    stats["created"] += 1
                else:
                    stats["updated"] += 1
                    
            except Exception as e:
                logger.error(f"Error processing airport row: {e}")
                stats["skipped"] += 1
                continue
        
        await self.db.commit()
        logger.info(f"Airports seeding complete: {stats}")
        return stats
    
    async def fetch_and_seed_airlines(self) -> Dict[str, int]:
        """
        Fetch airlines from OpenFlights and seed to database
        """
        logger.info("Fetching airlines from OpenFlights...")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(self.AIRLINES_URL)
            response.raise_for_status()
        
        # OpenFlights airlines.dat format:
        # Airline ID, Name, Alias, IATA, ICAO, Callsign, Country, Active
        reader = csv.reader(io.StringIO(response.text))
        
        stats = {"fetched": 0, "created": 0, "updated": 0, "skipped": 0}
        
        for row in reader:
            try:
                if len(row) < 8:
                    continue
                    
                airline_id, name, alias, iata, icao, callsign, country, active = row[:8]
                
                # Skip airlines without valid IATA codes
                if not iata or iata == "\\N" or iata == "-" or len(iata) != 2:
                    continue
                
                stats["fetched"] += 1
                
                is_active = active == "Y"
                
                # Determine if low-cost carrier (rough heuristic)
                is_low_cost = any(keyword in name.lower() for keyword in [
                    "ryan", "easy", "wizz", "spirit", "frontier", "allegiant",
                    "vueling", "pegasus", "jet2", "wow", "norwegian"
                ])
                
                result = await self.db.execute(text("""
                    INSERT INTO airlines (
                        iata_code, icao_code, name, country,
                        is_active, is_low_cost, logo_url
                    ) VALUES (
                        :iata, :icao, :name, :country,
                        :active, :low_cost, :logo
                    )
                    ON CONFLICT (iata_code) DO UPDATE SET
                        icao_code = COALESCE(EXCLUDED.icao_code, airlines.icao_code),
                        name = COALESCE(EXCLUDED.name, airlines.name),
                        country = COALESCE(EXCLUDED.country, airlines.country),
                        is_active = EXCLUDED.is_active,
                        updated_at = NOW()
                    RETURNING (xmax = 0) AS is_insert
                """), {
                    "iata": iata,
                    "icao": icao if icao != "\\N" else None,
                    "name": name,
                    "country": country if country != "\\N" else None,
                    "active": is_active,
                    "low_cost": is_low_cost,
                    "logo": f"https://pics.avs.io/100/100/{iata}.png"
                })
                
                row_result = result.fetchone()
                if row_result and row_result[0]:
                    stats["created"] += 1
                else:
                    stats["updated"] += 1
                    
            except Exception as e:
                logger.error(f"Error processing airline row: {e}")
                stats["skipped"] += 1
                continue
        
        await self.db.commit()
        logger.info(f"Airlines seeding complete: {stats}")
        return stats
    
    async def fetch_and_seed_routes(self) -> Dict[str, int]:
        """
        Fetch routes from OpenFlights and seed to database
        """
        logger.info("Fetching routes from OpenFlights...")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(self.ROUTES_URL)
            response.raise_for_status()
        
        # OpenFlights routes.dat format:
        # Airline, Airline ID, Source airport, Source airport ID, 
        # Dest airport, Dest airport ID, Codeshare, Stops, Equipment
        reader = csv.reader(io.StringIO(response.text))
        
        stats = {"fetched": 0, "created": 0, "updated": 0, "skipped": 0}
        
        # Aggregate routes to find airlines serving each route
        routes_dict: Dict[str, Dict[str, Any]] = {}
        
        for row in reader:
            try:
                if len(row) < 9:
                    continue
                    
                airline, airline_id, source, source_id, dest, dest_id, codeshare, stops, equipment = row[:9]
                
                # Skip invalid data
                if not source or source == "\\N" or len(source) != 3:
                    continue
                if not dest or dest == "\\N" or len(dest) != 3:
                    continue
                if not airline or airline == "\\N" or len(airline) > 3:
                    continue
                
                stats["fetched"] += 1
                
                route_key = f"{source}-{dest}"
                
                if route_key not in routes_dict:
                    routes_dict[route_key] = {
                        "origin_code": source,
                        "destination_code": dest,
                        "airlines": set(),
                        "is_direct": True,
                        "equipment": set()
                    }
                
                routes_dict[route_key]["airlines"].add(airline)
                if equipment and equipment != "\\N":
                    for eq in equipment.split(" "):
                        routes_dict[route_key]["equipment"].add(eq)
                
                # Check if any version has stops
                if stops and stops != "\\N" and int(stops) > 0:
                    routes_dict[route_key]["is_direct"] = False
                    
            except Exception as e:
                logger.debug(f"Error processing route row: {e}")
                stats["skipped"] += 1
                continue
        
        # Log aggregation results
        logger.info(f"Aggregated {len(routes_dict)} unique routes from {stats['fetched']} records (skipped {stats['skipped']} invalid)")
        
        if routes_dict:
            sample_route = list(routes_dict.items())[0]
            logger.info(f"Sample route: {sample_route[0]} = {sample_route[1]}")
        
        # Insert aggregated routes
        logger.info(f"Inserting {len(routes_dict)} unique routes...")
        
        insert_count = 0
        error_count = 0
        
        for route_key, route_data in routes_dict.items():
            try:
                airlines_list = list(route_data["airlines"])
                
                if insert_count == 0:
                    logger.info(f"First route to insert: {route_key} - airlines: {airlines_list}")
                
                # Also populate airport_destinations (denormalized)
                # Use raw SQL with escaped array literal to avoid parameter binding issues
                airlines_array_literal = "'{" + ",".join(airlines_list) + "}'" if airlines_list else "'{}'"
                origin_code = route_data["origin_code"]
                dest_code = route_data["destination_code"]
                is_direct = route_data["is_direct"]
                airline_count = len(airlines_list)
                
                # Use raw SQL without parameters for array
                sql = f"""
                    INSERT INTO airport_destinations (
                        airport_code, destination_code,
                        airlines_serving, airline_count, is_direct
                    ) VALUES (
                        '{origin_code}', '{dest_code}', {airlines_array_literal}, {airline_count}, {is_direct}
                    )
                    ON CONFLICT (airport_code, destination_code) DO UPDATE SET
                        airlines_serving = EXCLUDED.airlines_serving,
                        airline_count = EXCLUDED.airline_count,
                        is_direct = EXCLUDED.is_direct OR airport_destinations.is_direct,
                        updated_at = NOW()
                """
                await self.db.execute(text(sql))
                
                stats["created"] += 1
                insert_count += 1
                
                # Log progress every 1000 routes
                if insert_count % 1000 == 0:
                    logger.info(f"Inserted {insert_count} routes so far...")
                
            except Exception as e:
                error_count += 1
                if error_count <= 5:  # Only log first 5 errors
                    print(f"ERROR inserting route {route_key}: {type(e).__name__}: {e}", flush=True)
                    logger.error(f"Error inserting route {route_key}: {type(e).__name__}: {e}")
                stats["skipped"] += 1
                continue
        
        logger.info(f"Insert phase complete: {insert_count} inserted, {error_count} errors")
        await self.db.commit()
        logger.info(f"Routes seeding complete: {stats}")
        return stats
    
    async def update_destination_cities(self):
        """
        Update airport_destinations with city/country info from airports table
        """
        logger.info("Updating destination city/country info...")
        
        # Update all missing city/country/country_code from airports table
        result = await self.db.execute(text("""
            UPDATE airport_destinations ad
            SET 
                destination_city = COALESCE(ad.destination_city, a.city),
                destination_country = COALESCE(ad.destination_country, a.country),
                destination_country_code = COALESCE(ad.destination_country_code, a.country_code)
            FROM airports a
            WHERE ad.destination_code = a.iata_code
            AND (
                ad.destination_city IS NULL 
                OR ad.destination_country IS NULL 
                OR ad.destination_country_code IS NULL
                OR ad.destination_country_code = ''
            )
        """))
        
        await self.db.commit()
        logger.info("Destination city info updated")
    
    async def seed_all(self) -> Dict[str, Any]:
        """
        Seed all data: airports, airlines, routes
        """
        results = {
            "airports": await self.fetch_and_seed_airports(),
            "airlines": await self.fetch_and_seed_airlines(),
            "routes": await self.fetch_and_seed_routes(),
        }
        
        # Update city info
        await self.update_destination_cities()
        
        return results
