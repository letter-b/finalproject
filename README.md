# Retail Rental Analytics System

> What if the item that doesn't sell becomes an asset instead of waste?

---

## The Problem (and Why I Actually Care)

There's a production loop that doesn't make sense when you look at it directly. Brands manufacture at scale. Retailers stock at scale. Consumers buy, use a few times, and move on. Whatever doesn't sell gets discounted into the ground and eventually thrown away.

The UN's Global E-waste Monitor 2024 puts a number on the throwaway pile: 62 million tonnes of e-waste generated in 2022. That's up 82% from 2010, growing five times faster than formal recycling capacity, and on track to hit 82 million tonnes by 2030. The gap between what we generate and what we actually recover is widening, not closing.

Now here's where it gets interesting from a business angle: a meaningful share of that waste starts as unsold retail inventory. Products that don't find an immediate buyer enter the markdown road. A clearance markdown is what happens when a retailer gives up on selling a product at full price — they slash it by 30%, then 50%, then 70%, just to recover something and free up shelf space. The retailer loses margin. The brand loses perceived value. The customer gets a temporary deal. And the product, now worth a fraction of what it cost to make, is one step closer to the bin.

But the markdown isn't really where the problem starts. That is the last piece of the domino. The one that falls first is the brand releasing a new model — which makes last year's version obsolete, which forces the retailer to clear it, which destroys whatever residual value was left in a perfectly functional product. The markdown is the mechanism retailers reach for because there's no alternative. And once it's normalised, it feeds back into the production decision: if your product is going to be discounted and dumped anyway, why invest in making it last?

The business model *selects for* disposability. Cory Doctorow called this broader pattern enshittification in *Chokepoint Capitalism* — the way products degrade over time because the incentives stop pointing at quality and start pointing at extraction. Planned obsolescence isn't a conspiracy. It's just what happens when the model rewards it.

The rental model is a structural counter to all of that — and it works upstream, not just at the markdown end. If a product needs to survive multiple rental cycles to generate real revenue, durability stops being a cost centre and starts being a competitive advantage. A retailer still generating revenue from a two-year-old laptop has no urgency to clear it at 60% off. A brand that knows its products will be in circulation for 4–5 years has every reason to support them with software updates and spare parts. Companies stay responsible for products longer. The software gets patched. The hardware gets built to last. Less production. Less waste. Not as a side effect — as a direct consequence of the business model.

And there's a simpler, more human version of this argument too: there are things people *want* but can't justify owning. A proper camera for a weekend trip. A power tool for one project. A piece of luxury you'd never spend full price on but would absolutely try for a week. Rental unlocks those experiences. Less money spent by the customer, less new production required, and a revenue stream from inventory that was otherwise just depreciating on a shelf.

Companies win. Customers win. The world produces a little less. This project builds the data to test it.

---

## What the Data Shows

The electronics vertical is the core of the project. Items unsold for 12+ months were enrolled in a simulated rental programme and compared against a graduated clearance markdown — the realistic alternative a retailer would actually reach for. The dataset is fully synthetic, but every assumption — depreciation curves, operational costs, no-return rates, damage write-offs — was calibrated against real industry data and documented throughout the notebooks.

The headline: rental beats markdown in roughly 60% of cases under base assumptions. Under full stress testing — 10,000 Monte Carlo simulations varying every uncertain input simultaneously — rental won in 100% of runs, with a median revenue ratio of 1.93× against the markdown alternative.

The electronics vertical isn't the strongest case. That's maternity — where every customer already knows she only needs items for a few months, and the markdown alternative is genuinely weak. Or gardening, where Leroy Merlin Portugal already runs the programme today through 35+ stores. Each vertical has its own numbers, its own character, and its own reason why rental makes structural sense.

The through-line is the same: the longer a product can generate revenue in circulation, the less it needs to be discounted, and the less of it needs to be produced.

---

## Project Structure

```
finalproject/
│
├── notebooks/
│   ├── 01_data_generation.ipynb        # Builds the whole database from scratch
│   ├── 01B_*.ipynb                     # Vertical generators (furniture, maternity, gardening, luxury)
│   ├── 02_eda.ipynb                    # 12 sections of exploratory analysis
│   ├── 03_ab_testing.ipynb             # Three statistical tests
│   ├── 04_machine_learning.ipynb       # 3 models + sensitivity + Monte Carlo
│   └── live_feed_terminal_run.py       # Live demo script — trickles data into MySQL
│
├── data/
│   ├── generated_data/                 # 8 CSVs produced by notebook 01
│   ├── sql/                            # View definitions
│   └── tableau/                        # Flat files for Tableau
│
├── figures/                            # All chart outputs
│
├── rental_form/                        # Flask app — the write side of the system
│   ├── app.py
│   └── templates/
│
└── src/
    └── PowerBI/
        └── rental_final_project_analytics.pbix   # Live dashboard
```

---

## The Full Stack

This isn't just a notebook. The full pipeline is:

```
Python generates data
  → pandas DataFrames
    → SQLAlchemy + pymysql
      → MySQL tables (written automatically)
        → Views created on top of tables
          → Power BI reads views live
```

And there's a write side too:

```
Staff fills rental form (browser)
  → Flask receives the POST request
    → SQLAlchemy writes to MySQL
      → Views update automatically
        → Power BI reads the change live
```

Running `01_data_generation.ipynb` top to bottom rebuilds the entire database in under a minute. No Workbench. No manual imports. One line writes a full table:

```python
df.to_sql("products", con=engine, if_exists="replace", index=False)
```

This is a standard ETL pipeline (Extract, Transform, Load) — the same architecture used in production data engineering, just at a smaller scale.

---

## The Notebooks

### 01 · Data Generation

Generates 690 products, 2,000+ customers, and ~1,600 rental transactions. Exports everything to MySQL and CSV simultaneously. Run this once. Don't touch it unless you're regenerating.

Key decisions baked in:
- 12-month eligibility threshold — one full retail sales cycle
- Markdown depreciation tiers calibrated against SellCell and EverTrade IT asset data
- 10 product categories in the rental programme — 5 excluded (Wearables, Keyboards, Monitors, Networking, Peripherals) with documented rationale per category
- Musical Instruments added as category 15: strong real-world rental tradition, slow depreciation, wide price bands

### 01B · Vertical Generators

The same system tested across four other markets:

- **Furniture** — IKEA-style. Seasonal spikes, Feather/Furlenco ops cost benchmarks. The rental case is built on high ticket values and natural temporary use — expats, short-term renters, people furnishing a place they know they'll leave.

- **Maternity** — strongest rental case in the project. Every customer already knows she only needs items for a few months. The resale pool is narrow and buyers assume heavy wear. The markdown alternative is genuinely weak. The model doesn't need to work hard here — the customer's situation does most of the arguing.

- **Gardening** — built from scratch after finding that Leroy Merlin Portugal already runs a live garden tool rental service through 35+ stores via an Andaluga partnership. This isn't a hypothetical market. It exists. Rental durations are 1–3 days, no-return rate is the lowest in the project, and the seasonal patterns are clean.

- **Luxury** — most analytically interesting, and the one that inverts everything. A Hermès Birkin or a Rolex Submariner doesn't lose value sitting on a shelf — it often gains it. So the markdown baseline is near-retail (5% off at 12 months), not 60% off. Rental has to beat a strong target, not a weak one — which is why the win rate is lower. But when it wins, it wins much larger, because the rental rate on a €10,000 watch is substantial. And a meaningful share of customers here will never buy regardless of price — they're not choosing between buying and renting. Renting is the only realistic access. That's a structurally captive market.

All four use identical output schema so `02_eda.ipynb`, `03_ab_testing.ipynb`, and `04_machine_learning.ipynb` work unchanged with any vertical's data.

### 02 · EDA

12 sections. The one finding I keep coming back to: 30% of customers are repeat renters but drive 50% of revenue. Classic loyalty pattern — and it validates why the programme gets better over time, not worse.

### 03 · A/B Testing

Three formal tests. The important one is Section 3: a Welch's t-test comparing rental revenue vs markdown revenue. The result is statistically significant, but the test group sizes are unequal by design (~960 vs ~644) — because the pricing rule assignment reflects a realistic tiered rollout, not a clean 50/50 split.

### 04 · Machine Learning

Three models:

- **Random Forest** — predicts whether a product will be more profitable via rental *before* it enters the programme. Features are carefully chosen to avoid data leakage: `months_unsold_at_comparison` (available at programme entry), not `months_on_rental` (available only after).
- **Linear Regression** — projects monthly rental revenue forward 6 months. Caveat: linear trend on seasonal data has obvious limits; Prophet would be the production alternative.
- **Logistic Regression** — predicts customer churn risk. Churn is defined as >20% late returns OR any no-return on record. The chart shows predicted churn probability by segment, not raw coefficients — same model, clearer story.

Then two sections of stress testing:

- **Sensitivity Analysis** — three fixed scenarios (optimistic/realistic/pessimistic cost assumptions). The rental case holds in all three.
- **Monte Carlo** — 10,000 simulations varying all uncertain inputs simultaneously using triangular distributions. Scoped to programme categories only — the simulation tests what the programme actually covers, not the full product catalogue. Result: rental won in 100% of runs, with a median revenue ratio of 1.93× and a win rate range of 67.8%–74.7% across the 5th–95th percentile. That's the stress-tested floor, and it still holds comfortably.

### live_feed

Inserts 15 rental records per batch into MySQL, every 30 seconds, for 3 minutes, then auto-stops. Used for the live demo. Run it, switch to Power BI, click refresh, watch Total Rentals tick up.

```bash
python notebooks/live_feed_terminal_run.py
```

---

## The Rental Form

A Flask web app that serves as the operational layer — the write side of the system. Staff can log a new rental through a browser form. On submit, it writes directly to MySQL. Because Power BI is connected live, the dashboard updates on the next refresh.

This is the moment in the demo that makes the architecture click. The dashboard isn't just showing historical data — it's connected to a system that accepts new data in real time.

---

## Setup

**Requirements:** Python 3.11+, MySQL (local), Jupyter, Power BI Desktop

```bash
# Clone
git clone https://github.com/letter-b/finalproject
cd finalproject

# Virtual environment (using uv)
uv venv
source .venv/bin/activate        # Mac/Linux
.venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

Create a `.env` file in the root:

```
DB_HOST=localhost
DB_PORT=3306
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=rental_final_project
```

**Run order:**

```bash
# 1. Generate the database
jupyter notebook notebooks/01_data_generation.ipynb

# 2. Analysis (in order)
jupyter notebook notebooks/02_eda.ipynb
jupyter notebook notebooks/03_ab_testing.ipynb
jupyter notebook notebooks/04_machine_learning.ipynb

# 3. Open the dashboard
# Power BI: open src/PowerBI/rental_final_project_analytics.pbix
# Hit refresh — it reads from MySQL live

# 4. Optional: run the live feed for the full demo experience
python notebooks/live_feed_terminal_run.py
```

---

## Assumptions and Honest Limitations

The dataset is synthetic, but the rules behind it aren't. Every datapoint and vertical was built around documented market behaviour, because synthetic data is only as good as the rules it's built on. This means depreciation curves were calibrated against real resale market data, operational costs were benchmarked against companies already running rental programmes, seasonal patterns modelled on actual retail behaviour and the most crucial part: different rental rules were applied for different markets. The rules make sure the obvious is obvious: a luxury watch, a garden strimmer and a maternity pillow do not behave the same way, and pretending they do would break the model.

The system holds together precisely because each vertical was built with the most realistic knowledge of how that market works for each industry. Which also means it can be pointed at any new industry: research the rules, feed them in, and the architecture underneath doesn't change.

That said, the headline numbers are optimistic by design and documented as such throughout the notebooks:

- Operational costs are modelled at 15–28%. Real electronics rental operations run 35–50% all-in when storage, refurbishment, logistics, and customer acquisition are included.
- No storage or warehousing cost between rentals. In reality, downtime gaps generate cost.
- The markdown comparison uses the deepest realistic discount as the baseline — the ceiling, not the average.
- A 40–55% win rate is more realistic for real-world implementation. This model tests the upper bound under clean conditions.

The stress testing in Section 4b is where those assumptions get challenged. Under 10,000 Monte Carlo simulations varying every uncertain input simultaneously, rental won in 100% of runs. The floor is what matters — and it holds.

---

## Built With

Python · pandas · NumPy · SciPy · scikit-learn · SQLAlchemy · pymysql · Flask · MySQL · Power BI · Jupyter

---

## Closing Thoughts

I started this project with a question that genuinely annoyed me: why do perfectly functional products get discounted into irrelevance and thrown away, when there's an obvious alternative sitting right there?

Two weeks later — the final sprint of a two-month Ironhack data analytics bootcamp — I have an answer. Not a theory. A working system. Data generators calibrated against real market behaviour, a MySQL database that rebuilds itself in under a minute, statistical tests, three machine learning models, 10,000 Monte Carlo simulations, a live Power BI dashboard, a Flask app that writes to the same database the dashboard reads from, and five verticals proving the thesis isn't just an electronics story.

I didn't know what ETL meant when I started. I'd never touched Power BI, and I had no idea what SQLAlchemy was doing under the hood. I figured it out as I went, broke things, fixed them, broke them again, and somewhere in the middle of all that ended up building something I'm proud of.

The numbers held. Rental beat markdown in 100% of simulations. Not because I built the model to say yes — but because I built the rules to be honest, and the honest answer turned out to be yes.

What surprised me most wasn't the result. It was realising the architecture of what I did can answer endless "what if?" rental scenarios. Not just these ones. Swap the vertical, research the rules, feed them in. The system adapts. That magic and understanding of how all of the tools I've learned connect between them is the most valuable thing I can conclude. In my mind I just made the idea of a rental culture sexy, just like renting a DVD once was.

If you want to test it, break it, extend it, or adapt it to a new vertical — the repo is open, the architecture is documented, and I'd genuinely love to see where else it goes.

---

*Built as a final project for the Ironhack Data Analytics Bootcamp · April 2026*
