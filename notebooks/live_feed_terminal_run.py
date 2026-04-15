"""
🔴 Live Feed — Real-Time Rental Insertions
Inserts a batch of new rentals into MySQL every 30 seconds.
Auto-stops after 3 minutes. Go to Power BI → click Atualizar to see numbers change live.
"""

import time
import random
import datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

# =============================================================================
# CONFIGURATION
# =============================================================================
INTERVAL_SECONDS = 30    # How often to insert a batch
BATCH_SIZE       = 15    # Rentals per batch
VERBOSE          = True  # Print each batch to output
RUN_FOR_SECONDS  = 180   # Auto-stop after 3 minutes (change if needed)

# =============================================================================
# CONNECTION
# =============================================================================
load_dotenv()
engine = create_engine(
    f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}",
    echo=False
)

with engine.connect() as conn:
    count      = conn.execute(text("SELECT COUNT(*) FROM rentals")).scalar()
    n_products = conn.execute(text(
        # CURDATE() is intentional here — forward-looking live feed, not historical replay
    "SELECT COUNT(*) FROM products WHERE rental_eligible_date <= CURDATE()"
    )).scalar()
    n_customers = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar()
    n_rules     = conn.execute(text("SELECT COUNT(*) FROM pricing_rules")).scalar()

print(f"Connected to MySQL: {os.getenv('DB_NAME')}")
print(f"Current rentals in DB:      {count:,}")
print(f"Eligible products:          {n_products:,}")
print(f"Customers:                  {n_customers:,}")
print(f"Pricing rules:              {n_rules:,}")
print(f"Feed will start from rental #{count + 1}")

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def get_eligible_products(conn):
    result = conn.execute(text(
        "SELECT product_id, original_retail_price FROM products "
        "WHERE rental_eligible_date <= CURDATE()"  # intentional: forward-looking
    ))
    return result.fetchall()

def get_pricing_rules(conn):
    result = conn.execute(text(
        "SELECT rule_id, pricing_model, base_daily_rate, "
        "pct_of_retail_daily, late_fee_per_day, insurance_fee_pct "
        "FROM pricing_rules"
    ))
    return result.fetchall()

def generate_batch(conn, start_id, batch_size, n_customers):
    products = get_eligible_products(conn)
    rules    = get_pricing_rules(conn)
    batch    = []

    for i in range(batch_size):
        prod          = random.choice(products)
        product_id    = prod[0]
        retail_price  = prod[1]
        rule          = random.choice(rules)
        rule_id       = rule[0]
        pricing_model = rule[1]
        base_daily    = rule[2]
        pct_daily     = rule[3]
        late_fee_day  = rule[4]
        ins_pct       = rule[5]
        customer_id   = random.randint(1, n_customers)
        days_ago      = random.randint(0, 14)
        start_date    = datetime.date.today() - datetime.timedelta(days=days_ago)
        duration      = random.choice([7, 14, 21, 30])
        end_date      = start_date + datetime.timedelta(days=duration)
        base_rev      = round(base_daily * duration, 2) if pricing_model == "flat_rate" \
                        else round(pct_daily * retail_price * duration, 2)
        is_late       = random.random() < 0.13
        late_d        = random.randint(1, 7) if is_late else 0
        late_fee      = round(late_fee_day * late_d, 2) if is_late else 0.0
        ins_fee       = round(base_rev * ins_pct, 2)
        total         = round(base_rev + late_fee + ins_fee, 2)
        op_cost       = round(base_rev * random.uniform(0.15, 0.25), 2)
        no_ret        = random.random() < 0.055
        dbr           = no_ret and random.random() < 0.50  # DBR only occurs on no_ret
        net_rev       = 0.0 if no_ret else round(total - op_cost, 2)  # same result; cleaner
        exp_ret       = end_date + datetime.timedelta(days=late_d)
        act_ret       = exp_ret if not no_ret else None
        batch.append({
            "rental_id":                start_id + i,
            "product_id":               product_id,
            "customer_id":              customer_id,
            "pricing_rule_id":          rule_id,
            "rental_start_date":        start_date,
            "rental_end_date":          end_date,
            "expected_return_date":     exp_ret,
            "actual_return_date":       act_ret,
            "rental_duration_days":     duration,
            "base_rental_revenue":      base_rev,
            "late_fee":                 late_fee,
            "insurance_fee":            ins_fee,
            "total_rental_revenue":     total,
            "operational_cost":         op_cost,
            "net_rental_revenue":       net_rev,
            "is_no_return":             int(no_ret),
            "is_damaged_beyond_repair": int(dbr),
            "is_late":                  int(is_late),
        })
    return batch

def insert_batch(conn, batch):
    conn.execute(text("""
        INSERT INTO rentals (
            rental_id, product_id, customer_id, pricing_rule_id,
            rental_start_date, rental_end_date, expected_return_date,
            actual_return_date, rental_duration_days,
            base_rental_revenue, late_fee, insurance_fee,
            total_rental_revenue, operational_cost, net_rental_revenue,
            is_no_return, is_damaged_beyond_repair, is_late
        ) VALUES (
            :rental_id, :product_id, :customer_id, :pricing_rule_id,
            :rental_start_date, :rental_end_date, :expected_return_date,
            :actual_return_date, :rental_duration_days,
            :base_rental_revenue, :late_fee, :insurance_fee,
            :total_rental_revenue, :operational_cost, :net_rental_revenue,
            :is_no_return, :is_damaged_beyond_repair, :is_late
        )
    """), batch)
    conn.commit()

# =============================================================================
# LIVE FEED LOOP
# =============================================================================
print("=" * 55)
print("LIVE FEED STARTED")
print(f"Inserting {BATCH_SIZE} rentals every {INTERVAL_SECONDS} seconds")
print(f"Auto-stops after {RUN_FOR_SECONDS // 60} minutes")
print("Press Ctrl+C to stop early")
print("Then go to Power BI → click Atualizar (Refresh)")
print("=" * 55)

total_inserted = 0
batch_count    = 0
start_time     = time.time()

try:
    while True:
        # Auto-stop after RUN_FOR_SECONDS
        elapsed = time.time() - start_time
        if elapsed >= RUN_FOR_SECONDS:
            print(f"\nAuto-stopped after {RUN_FOR_SECONDS // 60} minutes.")
            break

        with engine.connect() as conn:
            max_id   = conn.execute(text("SELECT MAX(rental_id) FROM rentals")).scalar() or 0
            start_id = max_id + 1
            batch    = generate_batch(conn, start_id, BATCH_SIZE, n_customers)
            insert_batch(conn, batch)
            total_inserted += BATCH_SIZE
            batch_count    += 1
            new_total       = max_id + BATCH_SIZE

        if VERBOSE:
            batch_rev     = sum(r["total_rental_revenue"] for r in batch)
            remaining     = int(RUN_FOR_SECONDS - (time.time() - start_time))
            print(
                f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
                f"Batch #{batch_count}: +{BATCH_SIZE} rentals "
                f"(€{batch_rev:,.2f} revenue) | "
                f"Total in DB: {new_total:,} | "
                f"{remaining}s remaining → Hit Atualizar in Power BI"
            )

        time.sleep(INTERVAL_SECONDS)

except KeyboardInterrupt:
    print(f"\nStopped early after {batch_count} batches ({total_inserted} rentals inserted)")

print(f"\nDone. {total_inserted} rentals inserted across {batch_count} batches.")
