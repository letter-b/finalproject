# Retail Rental Analytics System

> What if the item that doesn't sell becomes an asset instead of waste?

---

## 🔗 Links

| | |
|---|---|
| 📊 **Notion — full project documentation** | [Process notes, decisions, architecture](https://www.notion.so/3439bd6f230f81128773f0275d237325) |
| 💻 **GitHub repo** | [github.com/letter-b/finalproject](https://github.com/letter-b/finalproject) |

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

## Key Results

| Metric | Value |
|---|---|
| Rental win rate | 62.7% of eligible products |
| Median revenue ratio | 1.54× vs clearance markdown |
| Monte Carlo (10,000 simulations) | Rental won in 100% of runs |
| Stress-tested median ratio | 1.93× (67.8%–74.7% win rate range) |
| Operational cost modelled | 15–28% (real-world: 35–50%) |

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

## The Database

8 tables, 4 analytical views. `rentals` is the central hub — it carries three foreign keys simultaneously (`product_id`, `customer_id`, `pricing_rule_id`) and stores all the business logic: revenue, costs, fees, flags, return dates.

```
categories ──────────< products >──────────────── rentals >──── customers
                           │                          │
                           │                          ├──< pricing_rules
                           ├──< inventory_events      └── return_conditions
                           └── rental_revenue_vs_discount
```

`rental_revenue_vs_discount` is the thesis table — one row per eligible product, rental revenue earned vs hypothetical markdown price, pre-computed and stored. This is where the win rate comes from.

> 📖 Full schema, relationship breakdown, and data modelling decisions → [Notion: Data Modelling](https://www.notion.so/3419bd6f230f812db92bea10eb6126e8)

---

## The Full Stack

```
Python generates data
  → pandas DataFrames
    → SQLAlchemy + pymysql
      → MySQL tables
        → Views
          → Power BI reads live
```

```
Staff fills rental form (browser)
  → Flask POST
    → SQLAlchemy writes to MySQL
      → Views update
        → Power BI reads the change live
```

Running `01_data_generation.ipynb` top to bottom rebuilds the entire database in under a minute. One line writes a full table:

```python
df.to_sql("products", con=engine, if_exists="replace", index=False)
```

The Tableau flat files in `data/tableau/` were built differently — a chain of `.merge()` calls that joins all tables in Python before writing to CSV, producing one denormalised row per rental (1,093 rows, 43 columns). When the project moved to Power BI, the CSVs were replaced by a live MySQL connection — the better architecture.

> 📖 Full pipeline explanation, ETL framing, live feed architecture → [Notion: How the Data Pipeline Works](https://www.notion.so/3419bd6f230f810ca1eed866e196316f)

---

## The Notebooks

### 01 · Data Generation
690 products, 2,000+ customers, ~1,600 rental transactions. Exports to MySQL and CSV simultaneously. Key decisions: 12-month eligibility threshold, markdown tiers from SellCell/EverTrade data, 10 categories in programme (5 excluded with rationale), Musical Instruments as category 15.

### 01B · Vertical Generators
Four additional markets — Furniture, Maternity (~78.7% win rate), Gardening (already live in Portugal via Leroy Merlin/Andaluga), and Luxury (inverted depreciation, near-retail markdown baseline). All use identical output schema — the analysis notebooks run unchanged on any vertical.

> 📖 Full vertical breakdowns, market research, and design decisions → [Notion: Portfolio Page](https://www.notion.so/3439bd6f230f81128773f0275d237325)

### 02 · EDA
12 sections. Key finding: 30% of customers are repeat renters but drive 50% of revenue. The programme gets better over time, not worse.

### 03 · A/B Testing
Three tests. The core one: Welch's t-test comparing rental vs markdown revenue. Groups are unequal by design (~960 vs ~644) because pricing model assignment reflects a realistic tiered rollout — expensive items skew toward `pct_of_retail`, cheap items toward `flat_rate`. Welch's is correct here precisely because the groups have unequal variance.

> 📖 Full A/B mechanics, the restaurant menu analogy, and how to defend it → [Notion: How the A/B Test Works](https://www.notion.so/3449bd6f230f812ba964ff49105c7574)

### 04 · Machine Learning
Three models: Random Forest (rental profitability classifier — data leakage fixed: uses `months_unsold_at_comparison`, not `months_on_rental`), Linear Regression (6-month revenue forecast), Logistic Regression (customer churn by segment). Plus Sensitivity Analysis across three cost scenarios and Monte Carlo (10,000 simulations, triangular distributions, scoped to programme categories only).

### live_feed
Inserts 15 rental records per batch into MySQL every 30 seconds for 3 minutes, then auto-stops. Run it, switch to Power BI, click refresh, watch Total Rentals tick up.

```bash
python notebooks/live_feed_terminal_run.py
```

---

## The Rental Form

A Flask web app — the write side of the system. Staff log a rental through a browser form; on submit it writes directly to MySQL. Because Power BI is connected live, the dashboard updates on the next refresh. This is the moment in the demo that makes the architecture click.

---

## Setup

**Requirements:** Python 3.11+, MySQL (local), Jupyter, Power BI Desktop

```bash
git clone https://github.com/letter-b/finalproject
cd finalproject

uv venv
source .venv/bin/activate        # Mac/Linux
.venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

`.env` file in root:

```
DB_HOST=localhost
DB_PORT=3306
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=rental_final_project
```

**Run order:**

```bash
jupyter notebook notebooks/01_data_generation.ipynb
jupyter notebook notebooks/02_eda.ipynb
jupyter notebook notebooks/03_ab_testing.ipynb
jupyter notebook notebooks/04_machine_learning.ipynb

# Dashboard: open src/PowerBI/rental_final_project_analytics.pbix → hit refresh

# Live demo:
python notebooks/live_feed_terminal_run.py
```

---

## Assumptions and Honest Limitations

The dataset is synthetic, but the rules behind it aren't. Depreciation curves calibrated against real resale data. Ops costs benchmarked against live rental companies. Seasonal patterns modelled on actual retail behaviour. Different rules for different markets — a luxury watch, a garden strimmer, and a maternity pillow do not behave the same way.

The headline numbers are optimistic by design and documented as such:

- Ops costs modelled at 15–28%. Real operations run 35–50% all-in.
- No storage cost between rentals. In reality, downtime gaps generate cost.
- The markdown comparison uses the deepest realistic discount — the ceiling, not the average.
- 40–55% win rate is more realistic for real-world implementation.

Under 10,000 Monte Carlo simulations varying every uncertain input simultaneously, rental won in 100% of runs. The floor is what matters — and it holds.

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
