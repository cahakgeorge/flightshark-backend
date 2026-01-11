# Flightshark Backend

Backend services for Flightshark - a flight search and group trip planning platform.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                       │
└─────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Gateway (Nginx)                         │
└─────────────────────────────────────────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI       │    │  Django Admin   │    │  Celery Workers │
│   (Main API)    │    │  (Content Mgmt) │    │  (Background)   │
└────────┬────────┘    └────────┬────────┘    └────────┬────────┘
         │                      │                      │
         └──────────────────────┼──────────────────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         ▼                      ▼                      ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Redis       │    │   PostgreSQL    │    │    MongoDB      │
│   (Cache/Q)     │    │ + TimescaleDB   │    │ (Scraped Data)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| **nginx** | 80, 443 | Load balancer & reverse proxy (optional in dev) |
| **api** | 8000 | FastAPI - Main API service |
| **admin** | 8001 | Django Admin - Content management |
| **worker** | - | Celery workers for background tasks |
| **beat** | - | Celery beat for scheduled tasks |
| **postgres** | 5432 | PostgreSQL + TimescaleDB |
| **mongo** | 27017 | MongoDB for scraped content |
| **redis** | 6379 | Redis for caching and queues |
| **rabbitmq** | 5672, 15672 | Message broker |
| **prometheus** | 9090 | Metrics collection |
| **grafana** | 3002 | Dashboards and visualization |
| **loki** | 3100 | Log aggregation |
| **promtail** | - | Log collector (scrapes Docker logs) |

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Make (optional, for convenience commands)

### Setup

```bash
# Clone the repository
git clone https://github.com/tenflux/flightshark-backend.git
cd flightshark-backend

# Copy environment file
cp .env.example .env

# Edit .env with your API keys (optional for development)
# vim .env

# Start all services
make setup

# Or manually:
docker compose up -d
```

### Access Points

- **API Docs**: http://localhost:8000/docs
- **Admin Panel**: http://localhost:8001/admin
- **RabbitMQ Management**: http://localhost:15672 (guest/guest)
- **Grafana**: http://localhost:3002 (admin/admin)
- **Prometheus** http://localhost:9090

### Create Admin User

```bash
# 1. Create Django migrations for app models (first time only)
docker compose exec admin python manage.py makemigrations destinations content users analytics

# 2. Run Django migrations
make admin-migrate

# 3. Create a Django admin superuser
make admin-superuser

# Or create superuser manually with specific credentials:
docker compose exec admin python manage.py shell -c "
from django.contrib.auth.models import User
User.objects.create_superuser('admin', 'admin@tenflux.com', 'admin123')
"
```

## Bootstrapping & Data Flow

This section explains the complete setup flow and which service handles what.

### Bootstrap Sequence

```
1. docker compose up -d
   │
   ├─► PostgreSQL starts
   │   └─► Runs init.sql (creates tables, TimescaleDB, seed data)
   │
   ├─► Redis, MongoDB, RabbitMQ start
   │
   ├─► FastAPI (api) starts
   │   └─► Connects to all databases
   │   └─► Exposes REST API on :8000
   │
   ├─► Django Admin starts
   │   └─► Requires: make admin-migrate (first time)
   │   └─► Requires: make admin-superuser (first time)
   │
   └─► Celery Worker/Beat start
       └─► Connects to RabbitMQ for task queue
       └─► Scheduled tasks begin (price updates, scraping)
```

### Data Initialization Responsibilities

| What | Service | Command/Trigger |
|------|---------|-----------------|
| **Core DB Schema** | PostgreSQL | Auto on startup (`init.sql`) |
| **TimescaleDB Setup** | PostgreSQL | Auto on startup (`init.sql`) |
| **Initial Airlines/Airports** | PostgreSQL | Auto on startup (`init.sql` seeds ~30) |
| **Django Auth Tables** | Django Admin | `make admin-migrate` |
| **Django App Tables** | Django Admin | `make admin-migrate` |
| **Bulk Reference Data** | FastAPI | `POST /admin/data/seed/openflights` |
| **Price Data** | Celery | Scheduled or `POST /admin/data/seed/popular-routes` |

### First-Time Setup (Complete Bootstrap)

```bash
# 1. Start all services
docker compose up -d

# 2. Wait for PostgreSQL to be healthy (~30 seconds)
docker compose logs postgres | tail -5

# 3. Run Django migrations (creates admin tables)
make admin-migrate

# 4. Create Django admin user
docker compose exec admin python manage.py shell -c "
from django.contrib.auth.models import User
User.objects.create_superuser('admin', 'admin@tenflux.com', 'admin123')
"

# 5. Seed reference data (airports, airlines, routes)
curl -X POST "http://localhost:8000/admin/data/seed/openflights?include_airports=true&include_airlines=true&include_routes=true"

# 6. Check seeding progress (~90 seconds for full seed)
curl "http://localhost:8000/admin/data/sync-status?limit=1"

# 7. Verify data (should show 144 destinations for Dublin)
curl "http://localhost:8000/admin/data/airport-destinations/DUB" | jq '.destinations_count'
```

### What Each Service Owns

| Service | Owns | Responsibilities |
|---------|------|------------------|
| **PostgreSQL** | Schema, core data | User accounts, trips, airports, airlines, routes, price history |
| **FastAPI (api)** | REST API, data seeding | All `/api/*` endpoints, search, auth, seeding endpoints |
| **Django Admin** | Content management | Admin UI, destination content, analytics dashboards |
| **Celery Workers** | Background jobs | Price updates, social scraping, notifications |
| **Celery Beat** | Scheduling | Triggers periodic tasks (every 15min, hourly, daily) |
| **MongoDB** | Scraped content | TikTok/Twitter/Instagram content, flight cache |
| **Redis** | Caching, sessions | Flight search cache, rate limiting, session storage |
| **RabbitMQ** | Task queue | Job distribution to Celery workers |

### Database Schema Management

| Database | Schema Management | Migration Command |
|----------|-------------------|-------------------|
| PostgreSQL (FastAPI models) | `init.sql` + manual | Direct SQL or Alembic |
| PostgreSQL (Django models) | Django ORM | `make admin-migrate` |
| MongoDB | Schemaless | Auto-created on insert |

### Verify Installation

```bash
# Check all services are running
docker compose ps

# Test API health
curl http://localhost:8000/health

# Test database connection
curl http://localhost:8000/ | jq '.database'

# Check data counts
curl "http://localhost:8000/airports/search?q=dublin" | jq '.[0]'
```

## API Endpoints

### Authentication
```
POST /auth/register    - Register new user
POST /auth/login       - Login, get JWT tokens
POST /auth/refresh     - Refresh access token
GET  /auth/me          - Get current user
```

### Flights
```
GET  /flights/search           - Search flights
GET  /flights/prices/{route}   - Price history
GET  /flights/cheapest-dates   - Cheapest dates for month
POST /flights/alerts           - Create price alert
```

### Trips
```
POST /trips                    - Create trip
GET  /trips                    - List user's trips
GET  /trips/{id}               - Get trip details
POST /trips/{id}/members       - Add member
POST /trips/{id}/search        - Search flights for group
```

### Destinations
```
GET  /destinations             - List destinations
GET  /destinations/{code}      - Destination details
GET  /destinations/{code}/social - Social media content
GET  /destinations/trending/   - Trending destinations
```

### Airports
```
GET  /airports/search?q=dublin - Search airports (autocomplete)
GET  /airports/{code}          - Get airport by IATA code
GET  /airports/city/{name}     - All airports in a city
GET  /airports/popular/        - List major airports
```

### Airlines
```
GET  /airlines/                - List all airlines
GET  /airlines/{code}          - Get airline by IATA code
GET  /airlines/{code}/routes   - Get airline's routes
GET  /airlines/routes/search   - Find airlines on a route
```

### Market Insights (Amadeus)
```
# Read Endpoints (cached, fast)
GET  /insights/traveled/{origin}       - Most traveled destinations from origin
GET  /insights/booked/{origin}         - Most booked destinations from origin
GET  /insights/busiest-periods/{origin} - Busiest months for travel
GET  /insights/trending                - Trending destinations (aggregated)
GET  /insights/popular-routes          - Popular routes worldwide

# Admin/Sync Endpoints (trigger data refresh)
POST /insights/sync/traveled           - Sync traveled data from Amadeus
POST /insights/sync/booked             - Sync booked data from Amadeus
POST /insights/sync/busiest            - Sync busiest periods from Amadeus
POST /insights/sync/trending           - Recalculate trending scores
POST /insights/sync/all                - Full sync (weekly task)
GET  /insights/sync/status             - View recent sync operations
```

## Database Schema

```
┌─────────────────────────────────────────────────────────────────────┐
│                        REFERENCE DATA                                │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │ airports │    │ airlines │    │ aircraft │    │  routes  │      │
│  │ (DUB,BCN)│    │ (FR,BA)  │    │ (738,320)│    │(DUB→BCN) │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         USER DATA                                    │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │  users   │───►│  trips   │───►│ members  │    │  alerts  │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     TIME-SERIES (TimescaleDB)                        │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  price_history: time | DUB→BCN | Ryanair | €49 | amadeus   │    │
│  └────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         ANALYTICS                                    │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │ searches │    │ popular  │    │conversion│    │  daily   │      │
│  │   logs   │    │  routes  │    │  events  │    │ metrics  │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

### Reference Data (PostgreSQL)

| Table | Description | Key Fields |
|-------|-------------|------------|
| **airports** | Airport reference data | `iata_code`, `city`, `country`, `lat/long`, `is_major` |
| **airlines** | Airline information | `iata_code`, `name`, `logo_url`, `alliance`, `is_low_cost` |
| **aircraft** | Aircraft types | `iata_code`, `name`, `manufacturer`, `typical_seats` |
| **routes** | Known flight routes | `origin_code`, `destination_code`, `airline_code`, `typical_price` |
| **destinations** | Curated city info | `airport_code`, `description`, `tags`, `highlights` |

### User Data (PostgreSQL)

| Table | Description | Key Fields |
|-------|-------------|------------|
| **users** | Registered users | `email`, `home_city`, `preferences` |
| **trips** | Group trips | `owner_id`, `destination_code`, `dates`, `status` |
| **trip_members** | Trip participants | `trip_id`, `user_id`, `origin_city`, `role` |
| **price_alerts** | Price notifications | `user_id`, `route`, `target_price`, `is_active` |

### Time-Series Data (PostgreSQL + TimescaleDB)

| Table | Description | Key Fields |
|-------|-------------|------------|
| **price_history** | Historical flight prices | `time`, `origin`, `destination`, `airline`, `price` |
| **price_daily_avg** | Aggregated daily prices | Auto-generated continuous aggregate |

### Analytics (PostgreSQL)

| Table | Description | Key Fields |
|-------|-------------|------------|
| **search_logs** | All flight searches | `origin`, `destination`, `results_count`, `response_time` |
| **popular_routes** | Trending routes | `route`, `search_count`, `rank`, `period` |
| **conversion_events** | Funnel tracking | `event_type`, `route`, `affiliate` |
| **daily_metrics** | Business metrics | `date`, `searches`, `users`, `revenue` |

### Scraped Content (MongoDB)

| Collection | Description |
|------------|-------------|
| **social_content** | TikTok/Twitter/Instagram posts |
| **flight_cache** | Cached flight search results |
| **destination_insights** | AI-generated insights |

### Seeded Data

The database is pre-seeded with:
- **30 major European airports** (DUB, LHR, BCN, CDG, etc.)
- **15 airlines** (Ryanair, BA, Lufthansa, easyJet, etc.)
- **14 sample routes** with typical pricing
- **11 aircraft types** (737, A320, 787, etc.)
- **30 days of mock price history**

## Django Admin Panel

The Django Admin (http://localhost:8001/admin) provides a beautiful, modern interface for managing:

### Reference Data Management 🌐
Manage all the core reference data that powers the platform:

| Section | What You Can Do |
|---------|-----------------|
| **Airports** | Add/edit airports, IATA/ICAO codes, coordinates, mark as major |
| **Airlines** | Manage airlines, logos, alliances, hub airports, ratings |
| **Routes** | Define flight routes, durations, typical prices, seasonal info |
| **Aircraft** | Aircraft types, manufacturers, seat counts |

### Destination Content 📍
- **Destinations** - Add/edit cities, descriptions, tags, images
- **Destination Tags** - Manage tag categories (sunny, adventure, party, etc.)
- **Best Booking Times** - Historical data about optimal booking windows
- **Social Content** - Moderate scraped TikTok/Twitter/Instagram content
- **Content Curations** - Create featured content collections

### User & Trip Management 👥
- **Flightshark Users** - View and manage registered users
- **Trips** - View all trips, members, and statuses
- **Price Alerts** - Monitor and manage user alerts
- **Emergency Contacts** - View notification contacts

### Analytics Dashboard 📊
- **Search Logs** - All flight searches with performance metrics
- **Popular Routes** - Trending routes with rankings
- **Conversion Events** - Funnel tracking data
- **Daily Metrics** - Aggregated business metrics

### Features ✨
- **Import/Export** airports, airlines, routes via CSV/Excel
- **Bulk actions** (mark airports as major, activate airlines, etc.)
- Beautiful Unfold theme with Material icons
- Advanced filtering and search
- Mobile-responsive design

### Adding New Reference Data

**Add a new airport:**
1. Go to Admin → Airports → Add Airport
2. Enter IATA code (e.g., `SFO`), name, city, country
3. Set coordinates for map display
4. Mark as "Major" for popular airports

**Add a new airline:**
1. Go to Admin → Airlines → Add Airline
2. Enter IATA code (e.g., `UA`), name, country
3. Add logo URL using Aviasales CDN: `https://pics.avs.io/100/100/{IATA_CODE}.png`
4. Set alliance and type (low-cost, charter, etc.)

**Add a new route:**
1. Go to Admin → Routes → Add Route
2. Enter origin/destination airport codes
3. Set typical duration, distance, and price range
4. Mark as seasonal if applicable

**Bulk import airports/airlines:**
1. Go to Admin → Airports or Airlines
2. Click "Import" button
3. Upload CSV with columns matching the model fields
4. Review and confirm import

## Data Seeding

The platform includes automated seeding from external data sources to quickly populate reference data.

### API Endpoints for Seeding

All seeding endpoints are under `/admin/data/`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/data/seed/openflights` | POST | Seed airports, airlines, and routes from OpenFlights.org |
| `/admin/data/seed/airport-destinations/{code}` | POST | Seed destinations from a specific airport (uses Amadeus) |
| `/admin/data/seed/all-major-airports` | POST | Seed destinations for all major airports |
| `/admin/data/seed/popular-routes` | POST | Seed popular routes with pricing data |
| `/admin/data/sync-status` | GET | View recent sync operations and their status |
| `/admin/data/airport-destinations/{code}` | GET | View seeded destinations from an airport |
| `/admin/data/popular-routes` | GET | View seeded popular routes |

### Quick Seed (Recommended)

Seed all reference data from OpenFlights.org (free, no API key needed):

```bash
# Seed airports, airlines, and routes in one call
curl -X POST "http://localhost:8000/admin/data/seed/openflights?include_airports=true&include_airlines=true&include_routes=true"

# Check progress
curl "http://localhost:8000/admin/data/sync-status?limit=1"
```

This seeds:
- **~6,000+ airports** worldwide with coordinates
- **~6,000+ airlines** with active status
- **~37,000+ routes** with airline information

### Seed from Amadeus (Requires API Key)

For pricing data and real-time route discovery:

```bash
# Set your Amadeus credentials in .env:
# AMADEUS_API_KEY=your_key
# AMADEUS_API_SECRET=your_secret
# AMADEUS_USE_TEST_API=true  # Use test API for development

# Seed destinations from a specific airport
curl -X POST "http://localhost:8000/admin/data/seed/airport-destinations/DUB"

# Seed popular routes with pricing
curl -X POST "http://localhost:8000/admin/data/seed/popular-routes?origins=DUB,LHR,CDG&destinations=BCN,LIS,AMS"
```

### View Seeded Data

```bash
# View destinations from Dublin
curl "http://localhost:8000/admin/data/airport-destinations/DUB"

# View popular routes
curl "http://localhost:8000/admin/data/popular-routes?origin=DUB"
```

### Scheduled Seeding (Celery)

Reference data is automatically refreshed by Celery beat:
- **Weekly** (Sunday 2 AM): Refresh all major airport destinations
- **Daily** (3:30 AM): Update popular routes with fresh pricing

### Data Sources

| Source | Data | Rate Limits | API Key |
|--------|------|-------------|---------|
| **OpenFlights.org** | Airports, airlines, routes | None (static data) | No |
| **Amadeus** | Real-time pricing, route discovery | Test: 500/month, Prod: varies | Yes |

## Development

### Makefile Commands

The `Makefile` provides shortcut commands for common Docker operations. It's a **developer convenience tool** - instead of typing long Docker commands, you use simple shortcuts.

#### Available Commands

| Command | What it does |
|---------|--------------|
| `make help` | Show all available commands |
| `make setup` | Initial setup (copy env, build, start services, migrate) |
| `make up` | Start all services |
| `make down` | Stop all services |
| `make restart` | Restart all services |
| `make logs` | View all logs |
| `make logs-api` | View API logs only |
| `make logs-admin` | View Django admin logs |

#### Database Commands

| Command | What it does |
|---------|--------------|
| `make migrate` | Run FastAPI/Alembic migrations |
| `make admin-migrate` | Run Django migrations |
| `make db-shell` | Open PostgreSQL shell |
| `make mongo-shell` | Open MongoDB shell |
| `make redis-cli` | Open Redis CLI |

#### Development Commands

| Command | What it does |
|---------|--------------|
| `make test` | Run all tests |
| `make lint` | Run linters |
| `make format` | Format code |
| `make shell-api` | Shell into API container |
| `make shell-admin` | Shell into Django container |

#### When to Use the Makefile

| Environment | Use Makefile? | Notes |
|-------------|---------------|-------|
| **Local Development** | ✅ Yes | Convenience, speed, standardized commands |
| **CI/CD Pipelines** | ⚠️ Sometimes | Can use, but often replaced with native CI commands |
| **Production Servers** | ❌ Rarely | Production uses orchestrators (K8s, ECS) or direct Docker Compose |

#### Production Deployment

In production, you typically bypass the Makefile and use Docker Compose directly with production overrides:

```bash
# Production deployment (on server)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The Makefile is essentially a documented cheat sheet for your project's commands - useful for onboarding new developers and daily development work.

### Running Tests
```bash
make test
```

### Code Quality
```bash
make lint      # Run linters
make format    # Format code
```

### Database Migrations
```bash
make migrate              # Run FastAPI migrations (Alembic)
make admin-migrate        # Run Django migrations
make makemigrations msg="Add new field"  # Create Alembic migration
make admin-makemigrations # Create Django migrations
```

### Shells
```bash
make shell-api     # Shell into API container
make shell-admin   # Shell into Django container
make db-shell      # PostgreSQL shell
make mongo-shell   # MongoDB shell
make redis-cli     # Redis CLI
```

## Background Tasks

### How It Works

Background tasks use **Celery** with **RabbitMQ** as the message broker:

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   FastAPI /     │  task   │    RabbitMQ     │  pull   │  Celery Workers │
│   Django Admin  │ ──────► │  (Task Queue)   │ ◄────── │  (Background)   │
└─────────────────┘         └─────────────────┘         └─────────────────┘
```

**Why RabbitMQ instead of Redis for task queue?**
- ✅ Strong message persistence (tasks won't be lost)
- ✅ Delivery guarantees (at-least-once delivery)
- ✅ Priority queues for critical tasks
- Redis is dedicated to caching, keeping concerns separated

### Scheduled Tasks (Celery Beat)
| Task | Schedule | Description |
|------|----------|-------------|
| update-popular-routes | Every 15 min | Update prices for popular routes |
| scrape-tiktok | Every hour | Scrape TikTok for destination content |
| scrape-twitter | Every 2 hours | Scrape Twitter for destination content |
| check-price-alerts | Every 30 min | Check and notify price alerts |
| send-checkin-reminders | Every hour | Send check-in reminders |
| generate-trending | Daily 3 AM | Generate trending insights |
| cleanup-old-data | Weekly Sun 4 AM | Clean up expired data |
| **market-insights-weekly** | **Weekly Sun 1 AM** | **Full Amadeus market insights sync** |
| calculate-trending-daily | Daily 5 AM | Recalculate trending scores |

### Manual Task Execution
```bash
# Run a task manually
docker compose exec worker celery -A celery_app call tasks.flight_prices.update_popular_routes

# Monitor tasks (Flower)
docker compose exec worker celery -A celery_app flower --port=5555
```

### RabbitMQ Management
Access the RabbitMQ dashboard at http://localhost:15672 (guest/guest) to:
- View active queues and messages
- Monitor worker connections
- Debug failed tasks

## External Integrations & Partners

### Flight Search Provider Architecture

The backend uses a **multi-provider architecture** with automatic failover for flight searches:

```
┌─────────────────────────────────────────────────────────────┐
│                    Provider Manager                          │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐                    │
│  │ Amadeus │ → │Skyscanner│ → │  Kiwi   │  (priority order)  │
│  │ (P1)    │   │  (P2)   │   │  (P3)   │                    │
│  └────┬────┘   └────┬────┘   └────┬────┘                    │
│       │             │             │                          │
│       └─────────────┼─────────────┘                          │
│                     │                                        │
│              ┌──────▼──────┐                                 │
│              │  Aggregated │                                 │
│              │   Results   │                                 │
│              └─────────────┘                                 │
└─────────────────────────────────────────────────────────────┘
```

**Search Strategies:**
- `fallback` - Try providers in priority order until one succeeds (fastest)
- `parallel` - Search all providers simultaneously (widest selection)
- `best_price` - Search all, deduplicate by cheapest (best value)

**Provider Features:**
- Automatic health tracking and failover
- Request rate limiting per provider
- Response time metrics
- Status monitoring endpoint: `GET /flights/providers/status`

### Flight Data Partners

| Partner | Integration | Use Case | Priority | Status |
|---------|-------------|----------|----------|--------|
| **Amadeus** | REST API | Primary flight search, pricing, route discovery | 1 | ✅ Active |
| **Skyscanner** | RapidAPI | Price comparison, meta-search aggregator | 2 | ✅ Ready |
| **Kiwi.com** | Tequila API | Multi-city, flexible dates, virtual interlining | 3 | ✅ Ready |

### Accommodation Partners

| Partner | Integration | Use Case | Status |
|---------|-------------|----------|--------|
| **Booking.com** | Affiliate API | Hotel search, accommodation booking | 🔄 Planned |

### Market Insights (Amadeus Travel Intelligence)

The system uses **Amadeus Market Insights APIs** to provide travel trends and analytics:

| API | Data Provided | Update Frequency |
|-----|---------------|------------------|
| **Flight Most Traveled** | Top destinations by traffic | Weekly |
| **Flight Most Booked** | Top destinations by bookings | Weekly |
| **Flight Busiest Period** | Busiest months for travel | Weekly |

**How it works:**

1. **Weekly Sync** (Sunday 1 AM UTC): Celery task fetches data from Amadeus for major origins
2. **Storage**: Data stored in PostgreSQL with full historical tracking
3. **Caching**: Results cached in Redis (24h for traveled/booked, 1h for trending)
4. **Trending Calculation**: Daily aggregation of traveled + booked scores

**API Usage:**

```bash
# Get most traveled destinations from Dublin
curl "http://localhost:8000/insights/traveled/DUB?limit=20"

# Get trending destinations globally
curl "http://localhost:8000/insights/trending?origin=GLOBAL"

# Get busiest months for London departures
curl "http://localhost:8000/insights/busiest-periods/LHR?direction=DEPARTING"

# Manually trigger full sync (admin)
curl -X POST "http://localhost:8000/insights/sync/all"
```

**Database Tables:**
- `traveled_destinations` - Most traveled destinations per origin
- `booked_destinations` - Most booked destinations per origin
- `busiest_travel_periods` - Busiest months per origin
- `trending_destinations` - Aggregated trending scores
- `market_insights_sync_log` - Sync operation tracking

### Reference Data Sources

| Source | Data | API Key Required |
|--------|------|------------------|
| **OpenFlights.org** | Airports, airlines, routes (static) | No |
| **Amadeus** | Real-time pricing, route discovery, market insights | Yes |

### Social Media
- **TikTok** - Travel content (unofficial scraping)
- **Twitter/X** - Travel mentions and trends
- **Instagram** - Destination content

### Notifications
- **SendGrid** - Transactional emails (price alerts, confirmations)
- **Twilio** - SMS notifications (optional)

## Environment Variables

See `.env.example` for all available configuration options.

Key variables:
```bash
# Required for production
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
MONGODB_URL=mongodb://...

# ================================
# Flight Search Providers
# ================================
# The system supports multiple providers with automatic failover.
# Configure at least one for real flight data.

# Search strategy: "fallback" (try in order), "parallel" (all at once), "best_price" (cheapest per route)
FLIGHT_SEARCH_STRATEGY=fallback

# Primary: Amadeus (https://developers.amadeus.com/)
# Free tier: ~2000 calls/month
AMADEUS_API_KEY=your-amadeus-api-key
AMADEUS_API_SECRET=your-amadeus-api-secret
AMADEUS_USE_TEST_API=true  # Set to false for production API

# Secondary: Skyscanner (via RapidAPI - https://rapidapi.com/skyscanner/api/skyscanner-flight-search)
# Great for price comparison, meta-search
SKYSCANNER_API_KEY=your-rapidapi-skyscanner-key

# Tertiary: Kiwi.com (https://tequila.kiwi.com/)
# Free tier: 1000 calls/day. Excellent for multi-city and flexible dates
KIWI_API_KEY=your-kiwi-tequila-key

# ================================
# Other Integrations
# ================================

# Notifications (optional)
SENDGRID_API_KEY=your-sendgrid-api-key
```

## Load Balancer (Nginx)

The project includes a production-ready Nginx configuration for:
- **Load balancing** across multiple API instances
- **SSL termination** (HTTPS)
- **Rate limiting** (30 req/s general, 10 req/s for searches)
- **Security headers**
- **Gzip compression**
- **WebSocket support**

### Development (without Nginx)

By default, services are accessed directly:
```bash
make up
# API: http://localhost:8000
# Admin: http://localhost:8001
```

### Development (with Nginx)

To test Nginx locally:
```bash
docker compose --profile with-nginx up -d
# All traffic: http://localhost (port 80)
# Admin: http://localhost:8080
```

### Production (with Nginx + SSL)

1. **Get SSL certificates** (Let's Encrypt):
```bash
certbot certonly --standalone -d api.flightshark.com -d admin.flightshark.com
cp /etc/letsencrypt/live/api.flightshark.com/* infrastructure/nginx/certs/
```

2. **Enable SSL** in `infrastructure/nginx/nginx.conf`:
   - Uncomment the `listen 443 ssl` lines
   - Uncomment the `ssl_certificate` lines

3. **Deploy**:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Scaling API Horizontally

Edit `docker-compose.prod.yml` to add more API instances:
```yaml
api-2:
  extends:
    service: api
  container_name: flightshark-api-2
```

Then update `nginx.conf` upstream:
```nginx
upstream api_servers {
    least_conn;
    server api:8000;
    server api-2:8000;
    server api-3:8000;
}
```

## Monitoring & Observability

The backend includes a full observability stack:
- **Prometheus** - Metrics collection
- **Grafana** - Dashboards and visualization  
- **Loki** - Log aggregation
- **Promtail** - Log collector

### Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3002 | admin / admin |
| Prometheus | http://localhost:9090 | - |
| Loki | http://localhost:3100 | - |

### Viewing Logs in Grafana (Loki)

1. **Open Grafana**: http://localhost:3002
2. **Navigate to Explore**: Click the compass icon in the left sidebar
3. **Select Loki**: Choose "Loki" from the data source dropdown
4. **Run LogQL queries**:

```logql
# All API service logs
{service="api"}

# Filter for errors
{service="api"} |= "ERROR"

# Filter for specific endpoint
{service="api"} |= "register"

# All Django admin logs
{service="admin"}

# Filter by log level
{service="api"} | json | level="error"

# Search across all services
{job="docker"} |= "exception"
```

#### Create a Logs Dashboard Panel

1. Go to **Dashboards** → **New** → **New Dashboard**
2. Click **"Add visualization"**
3. Select **Loki** as the data source
4. Enter your LogQL query
5. Choose **"Logs"** visualization type
6. Configure:
   - **Time** field for timestamp
   - Enable **"Wrap lines"** for readability
   - Set appropriate **deduplication** if needed
7. Click **"Apply"**

### Viewing Metrics in Grafana (Prometheus)

1. **Open Grafana**: http://localhost:3002
2. **Navigate to Explore**: Click the compass icon
3. **Select Prometheus**: Choose "Prometheus" from the dropdown
4. **Run PromQL queries**:

```promql
# Total HTTP requests
http_requests_total

# Requests per second (rate over 5 minutes)
rate(http_requests_total[5m])

# Request latency (95th percentile)
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Requests grouped by endpoint
sum by (endpoint) (http_requests_total)

# Requests grouped by status code
sum by (status) (http_requests_total)

# Error rate (5xx responses)
sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))

# Average response time
rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])
```

#### Create a Metrics Dashboard Panel

1. Go to **Dashboards** → **New** → **New Dashboard**
2. Click **"Add visualization"**
3. Select **Prometheus** as the data source
4. Enter your PromQL query
5. Choose visualization type:
   - **Time series** - For trends over time
   - **Stat** - For single current values
   - **Gauge** - For values with thresholds
   - **Bar chart** - For comparing categories
6. Configure panel options:
   - Set **title** and **description**
   - Configure **legend** and **axes**
   - Add **thresholds** for alerts
7. Click **"Apply"**

### Useful Pre-built Queries

#### API Performance Dashboard

| Panel Name | Query | Visualization |
|------------|-------|---------------|
| Requests/sec | `rate(http_requests_total[1m])` | Time series |
| Error Rate % | `sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100` | Gauge |
| P95 Latency | `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))` | Time series |
| Requests by Endpoint | `sum by (endpoint) (increase(http_requests_total[1h]))` | Bar chart |

#### System Health Dashboard

| Panel Name | Query | Visualization |
|------------|-------|---------------|
| API Logs | `{service="api"}` (Loki) | Logs |
| Error Logs | `{service="api"} |= "ERROR"` (Loki) | Logs |
| Active Targets | `up` | Stat |

### Prometheus Direct Access

Access Prometheus UI directly at http://localhost:9090:

1. **Targets**: Check which services are being scraped
   - Go to Status → Targets
   - Verify `flightshark-api` shows "UP"

2. **Graph**: Run queries interactively
   - Enter query in expression box
   - Click "Execute"
   - Switch between "Table" and "Graph" views

3. **Alerts**: View configured alert rules
   - Go to Alerts tab

### Troubleshooting

**Logs not appearing in Loki?**
```bash
# Check Promtail is running
docker compose ps promtail

# View Promtail logs
docker compose logs promtail --tail=50

# Verify Loki is receiving data
curl -s "http://localhost:3100/loki/api/v1/labels"
```

**Metrics not appearing in Prometheus?**
```bash
# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Verify API exposes metrics
curl -s http://localhost:8000/metrics | head -20
```

**Grafana can't connect to data sources?**
```bash
# Restart Grafana to reload provisioned datasources
docker compose restart grafana

# Check datasource configuration
cat infrastructure/grafana/provisioning/datasources/datasources.yml
```

## Deployment

### Digital Ocean (Docker Compose)
```bash
# On your droplet
git clone ...
cd flightshark-backend
cp .env.example .env
# Edit .env with production values
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### AWS Migration Path
- PostgreSQL → RDS
- Redis → ElastiCache
- MongoDB → MongoDB Atlas or DocumentDB
- Containers → ECS or EKS
- Nginx → Application Load Balancer (ALB)

## License

Proprietary - Tenflux Limited


