# Rental Decision Engine — Flask Web App

A data entry form that lets you create a new rental, computes the **rental vs markdown verdict** in real time, writes to MySQL, and Power BI updates on refresh.

## Setup

```bash
# 1. Copy your .env from the main project (or create from template)
cp .env.example .env
# Edit .env with your MySQL credentials

# 2. Install dependencies (already installed if you have the main project)
pip install flask pymysql sqlalchemy python-dotenv

# 3. Run
python app.py
```

## Open in browser

```
http://localhost:5050
```

## What it does

1. **Products dropdown** — loads all rental-eligible products from your MySQL database, grouped by category. Shows retail price alongside each product name.

2. **Duration slider** — 1–90 days with quick preset buttons (7d / 14d / 30d / 60d).

3. **Quantity slider** — 1–10 units.

4. **Customer dropdown** — filterable by segment (Business / Professional / Student / Casual).

5. **Live preview** — as you change inputs, the right panel instantly shows:
   - Daily rate, base revenue, insurance fee, late fee income
   - Operational cost (18.5%), expected damage cost
   - Net revenue per unit and total
   - Markdown comparison (graduated discount based on months unsold)
   - Revenue ratio and **✅ Rental wins / ❌ Markdown wins** verdict

6. **Submit** — writes the rental(s) to your MySQL `rentals` table and an event to `inventory_events`. Power BI updates on next Refresh click.

7. **Live stats strip** (header) — shows current Total Rentals, Win Rate, Avg Ratio, Avg Revenue from the live database. Refreshes every 30 seconds.

## If MySQL is offline

The app works in preview-only mode using demo products and local calculations. You'll see a warning banner at the top. All calculations are the same — you just can't write to the DB.

## How it fits the pipeline

```
You fill in the form
    ↓
Flask computes verdict (same logic as 01_data_generation.ipynb)
    ↓
Writes to MySQL rentals + inventory_events tables
    ↓
Power BI → click Refresh
    ↓
Total Rentals ticks up, Win Rate recalculates, charts update
```

The downstream stack doesn't change at all — this is just a friendlier front door than running a notebook.
