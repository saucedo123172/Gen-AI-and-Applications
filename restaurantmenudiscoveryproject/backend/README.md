# Backend

FastAPI service: restaurant discovery (Google Places) -> menu extraction
(structured data / PDF / LLM fallback) -> Postgres+pgvector storage -> search API.

## Setup

1. Create a [Supabase](https://supabase.com) project (free tier), then in its
   SQL editor run: `create extension if not exists vector;`
2. Copy `.env.example` to `.env` and fill in `GOOGLE_MAPS_API_KEY`,
   `ANTHROPIC_API_KEY`, and `DATABASE_URL` (from Supabase's connection string).
3. Install dependencies:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. Run the API:
   ```bash
   uvicorn app.main:app --reload
   ```
   This creates the DB tables on startup if they don't exist yet.

## Ingesting a test area

Ingestion is a manual/offline step, not something the mobile app triggers.
With the server running:

```bash
curl -X POST "http://localhost:8000/restaurants/ingest?area_query=The+Galleria,+Houston,+TX&radius_m=1500"
curl -X POST "http://localhost:8000/restaurants/ingest?area_query=77004&radius_m=2000"
```

## Querying

```bash
curl "http://localhost:8000/restaurants"
curl "http://localhost:8000/restaurants/search?q=vegan+appetizer&max_price=15"
```

Both endpoints only return restaurants where `menu_status = found`.
