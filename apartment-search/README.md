# Israel Apartment Search

Mobile-first apartment rental search app for Israel. Searches Yad2 and Madlan with fully customizable filters.

## Features

- **Search filters**: price range, rooms, floors, city, neighborhood
- **Live scraping**: pull fresh listings from Yad2 & Madlan on demand
- **Manual listings**: add listings from any source (Facebook Marketplace, etc.) manually
- **Favorites**: save listings with a heart tap
- **Sorting**: by date, price, rooms, floor, size
- **Mobile-first** responsive UI with Hebrew text support
- **Docker** deployment in two commands

## Tech Stack

| Layer    | Technology |
|----------|-----------|
| Frontend | React 18, Vite, Tailwind CSS |
| Backend  | Python 3.11, FastAPI, aiosqlite |
| Scrapers | httpx, BeautifulSoup4 |
| DB       | SQLite (zero-config) |
| Deploy   | Docker Compose |

## Quick Start

### Local Development

**Backend**
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev        # opens http://localhost:3000
```

### Docker (Production)

```bash
docker-compose up --build
# Frontend → http://localhost:3000
# Backend API → http://localhost:8000/docs
```

## Usage

1. **Scan Now** — triggers fresh scraping from Yad2 and Madlan using your current filter settings
2. **Search** — queries the local database with any combination of filters
3. **Add** tab — manually add a listing you found elsewhere (Facebook, WhatsApp groups, etc.)
4. **Heart icon** on any card — saves it to your Saved tab

## API Reference

FastAPI auto-generates docs at `http://localhost:8000/docs`.

Key endpoints:
- `POST /api/scrape/start` — start a scrape job with filters
- `GET  /api/scrape/status/{job_id}` — poll job completion
- `GET  /api/listings/` — query saved listings with filters
- `POST /api/listings/manual` — add a listing manually
- `PATCH /api/listings/{id}/favorite` — toggle saved

## Facebook Marketplace

Facebook actively blocks automated scraping and bypassing their security is against their Terms of Service. Instead, use the **Add Listing Manually** tab to save Facebook listings by copy-pasting the relevant details. The form accepts price, rooms, floor, images, contact info, and a direct URL link.

## Supported Cities (Yad2)

The scraper maps city names to Yad2's internal city codes. Supported:
תל אביב, ירושלים, חיפה, ראשון לציון, פתח תקווה, אשדוד, נתניה, באר שבע, בני ברק, חולון, רמת גן, אשקלון, רחובות, בת ים, כפר סבא, הרצליה, חדרה, מודיעין, לוד, אילת — and their English equivalents.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `apartments.db` | Path to the SQLite database file |
| `VITE_API_URL` | `/api` | Backend API base URL (frontend) |
