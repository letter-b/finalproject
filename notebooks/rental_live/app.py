import os
from flask import Flask, render_template, jsonify, request
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ── DB ─────────────────────────────────────────
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "rental_final_project")

def get_engine():
    return create_engine(
        f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}",
        pool_pre_ping=True
    )

# ── Business assumptions ────────────────────────
# Matches notebook 01: OPS_COST midpoint of uniform(0.15, 0.25)
# DAMAGE: 2.8% of retail price per rental cycle
OPS_COST = 0.185
DAMAGE   = 0.028

# ── Minimum rental duration by category ────────
# min_days:      absolute floor — form cannot go below this
# friendly_days: recommended sweet spot shown to the customer
MIN_RENTAL_BY_CATEGORY = {
    "Smartphones":         {"min_days":  3, "friendly_days":  7},
    "Laptops":             {"min_days":  5, "friendly_days":  7},
    "Tablets":             {"min_days":  5, "friendly_days":  7},
    "Drones":              {"min_days":  3, "friendly_days":  7},
    "Audio":               {"min_days":  3, "friendly_days":  7},
    "Gaming":              {"min_days":  3, "friendly_days":  7},
    "Cameras":             {"min_days":  3, "friendly_days":  7},
    "TVs":                 {"min_days":  7, "friendly_days": 30},
    "Musical Instruments": {"min_days":  7, "friendly_days": 30},
    # Appliances: tiered by price — see get_appliance_min_days()
    "Appliances":          {"min_days": 30, "friendly_days": 30},  # default, overridden at runtime
}
DEFAULT_MIN = {"min_days": 3, "friendly_days": 7}

# Appliance minimum rental days — tiered by retail price
# <100 EUR  -> 7 days  (cheap items, short loan makes sense)
# 100-200   -> 30 days (mid-range, monthly minimum)
# >200      -> 60 days (expensive appliances, 2-month minimum)
def get_appliance_min_days(price: float) -> dict:
    if price < 100:
        return {"min_days":  7, "friendly_days":  7}
    elif price <= 200:
        return {"min_days": 30, "friendly_days": 30}
    else:
        return {"min_days": 60, "friendly_days": 60}

# Revenue cap: a single rental cycle should never exceed 35% of retail price.
# Only triggers for cheap items rented for long durations (e.g. €100 appliance
# at 60 days). For high-value items the flat rate pricing stays well below this
# ceiling naturally. Ensures the customer always saves vs buying outright.
RENTAL_CYCLE_CAP_PCT = 0.35

def get_rental_cap_pct(days: int) -> float:
    return RENTAL_CYCLE_CAP_PCT

# ── Pricing model selector ──────────────────────
def choose_pricing_model(price: float) -> str:
    return "pct_of_retail" if price > 500 else "flat_rate"

def get_pricing_rule(conn, price: float):
    return conn.execute(text("""
        SELECT rule_id, pricing_model, base_daily_rate,
               pct_of_retail_daily, late_fee_per_day, insurance_fee_pct
        FROM pricing_rules
        WHERE pricing_model = :pm
        ORDER BY rule_id
        LIMIT 1
    """), {"pm": choose_pricing_model(price)}).fetchone()

# ── Markdown depreciation ───────────────────────
# Mirrors get_discount() in notebook 01 Cell 19 exactly.
MARKDOWN_TIERS = {
    "fast":     [(12, 0.45), (18, 0.55), (24, 0.70), (999, 0.75)],
    "standard": [(12, 0.35), (18, 0.45), (24, 0.65), (999, 0.72)],
    "slow":     [(12, 0.25), (18, 0.35), (24, 0.55), (999, 0.65)],
}

def get_markdown_price(retail_price: float, months_unsold: float, dep_class: str) -> float:
    tiers = MARKDOWN_TIERS.get(dep_class, MARKDOWN_TIERS["standard"])
    for threshold, discount_pct in tiers:
        if months_unsold <= threshold:
            return round(retail_price * (1 - discount_pct), 2)
    return round(retail_price * 0.25, 2)

def get_discount_pct(months_unsold: float, dep_class: str) -> float:
    tiers = MARKDOWN_TIERS.get(dep_class, MARKDOWN_TIERS["standard"])
    for threshold, discount_pct in tiers:
        if months_unsold <= threshold:
            return discount_pct
    return 0.75

# ── Expected rentals ────────────────────────────
def estimate_expected_rentals(months_unsold: float, price: float) -> int:
    if months_unsold < 15:
        expected = 4
    elif months_unsold < 20:
        expected = 3
    else:
        expected = 2

    if price > 1500:
        expected += 1   # expensive items are more desirable for rental
    elif price < 250:
        expected -= 1   # cheap items — people just buy them

    return max(2, min(expected, 5))

# ── Core computation ────────────────────────────
# Returns two clearly separated views of the same transaction:
#
#   customer — what the renter pays and how much they save vs buying outright
#   store    — what the retailer earns, costs, and gains vs a clearance markdown
#
def compute_summary(price: float, rule, days: int, qty: int,
                    months: float, dep_class: str = "standard",
                    category_name: str = ""):

    if rule is None:
        raise ValueError("No pricing rule found")

    # ── Per-rental revenue ──
    if rule.pricing_model == "pct_of_retail":
        daily_rate = float(price) * float(rule.pct_of_retail_daily or 0)
    else:
        daily_rate = float(rule.base_daily_rate or 0)

    base_revenue  = daily_rate * days
    insurance_fee = base_revenue * float(rule.insurance_fee_pct or 0)
    gross_revenue = base_revenue + insurance_fee   # total the customer pays per cycle

    # Flat cap: no single rental cycle exceeds 35% of retail.
    # Only bites cheap items on long rentals — high-value items never reach this.
    gross_cap     = price * get_rental_cap_pct(days)
    cap_applied   = gross_revenue > gross_cap
    if cap_applied:
        # Scale base and insurance proportionally so the breakdown still adds up
        scale         = gross_cap / gross_revenue
        base_revenue  = round(base_revenue  * scale, 2)
        insurance_fee = round(insurance_fee * scale, 2)
        gross_revenue = round(gross_cap, 2)

    # ── Store costs per cycle ──
    ops_cost    = gross_revenue * OPS_COST          # handling, cleaning, admin
    damage_cost = price * DAMAGE                    # damage reserve
    net_revenue = gross_revenue - ops_cost - damage_cost

    # ── Markdown comparison ──
    markdown_price = get_markdown_price(price, months, dep_class)
    discount_pct   = get_discount_pct(months, dep_class)

    # ── Lifetime value ──
    expected_rentals      = estimate_expected_rentals(months, price)
    lifetime_rental_value = net_revenue * expected_rentals

    verdict = "rental" if lifetime_rental_value > markdown_price else "markdown"
    ratio   = round(lifetime_rental_value / markdown_price, 2) if markdown_price else 0

    # ── Duration rules for this category ──
    if category_name == "Appliances":
        duration_rules = get_appliance_min_days(price)
    else:
        duration_rules = MIN_RENTAL_BY_CATEGORY.get(category_name, DEFAULT_MIN)

    # ────────────────────────────────────────────
    # CUSTOMER VIEW
    # What does the renter pay? What do they save vs buying outright?
    # ────────────────────────────────────────────
    customer_total       = round(gross_revenue * qty, 2)
    saving_vs_buying     = round((price - gross_revenue) * qty, 2)
    saving_pct           = round((1 - gross_revenue / price) * 100, 1) if price else 0

    # ────────────────────────────────────────────
    # STORE VIEW
    # What does the retailer earn after costs? How does it compare to marking down?
    # ────────────────────────────────────────────
    store_gross          = round(gross_revenue * qty, 2)
    store_ops_total      = round(ops_cost * qty, 2)
    store_damage_total   = round(damage_cost * qty, 2)
    store_net_cycle      = round(net_revenue * qty, 2)
    store_net_lifetime   = round(lifetime_rental_value * qty, 2)
    store_markdown_total = round(markdown_price * qty, 2)
    store_advantage      = round((lifetime_rental_value - markdown_price) * qty, 2)

    return {
        # ── Raw figures (DB insert & internal use) ──
        "daily_rate":             round(daily_rate, 2),
        "base_revenue":           round(base_revenue, 2),
        "insurance_fee":          round(insurance_fee, 2),
        "late_fee_income":        0.0,
        "gross_revenue":          round(gross_revenue, 2),
        "ops_cost":               round(ops_cost, 2),
        "damage_cost":            round(damage_cost, 2),
        "net_per_unit":           round(net_revenue, 2),
        "markdown_price":         markdown_price,
        "expected_rentals":       expected_rentals,
        "lifetime_rental_value":  round(lifetime_rental_value, 2),
        "ratio":                  ratio,
        "verdict":                verdict,
        "retail_price":           round(price, 2),
        "dep_class":              dep_class,
        "months_unsold":          round(months, 1),
        "discount_pct":           round(discount_pct * 100, 0),

        # ── Duration rules ──
        "min_days":               duration_rules["min_days"],
        "friendly_days":          duration_rules["friendly_days"],
        "cap_applied":            cap_applied,

        # ── CUSTOMER VIEW ──────────────────────────
        "customer": {
            "daily_rate":         round(daily_rate, 2),
            "base_charge":        round(base_revenue, 2),
            "insurance_fee":      round(insurance_fee, 2),
            "total_payment":      customer_total,         # what they pay for this rental
            "retail_price":       round(price * qty, 2),  # what it would cost to buy
            "saving_vs_buying":   saving_vs_buying,       # money saved vs buying outright
            "saving_pct":         saving_pct,             # saving as % of retail
            "duration_days":      days,
            "quantity":           qty,
        },

        # ── STORE VIEW ─────────────────────────────
        "store": {
            "gross_revenue":      store_gross,            # received from customer
            "ops_cost":           store_ops_total,        # handling, admin, cleaning
            "damage_reserve":     store_damage_total,     # damage provision
            "net_this_cycle":     store_net_cycle,        # net profit this rental only
            "expected_rentals":   expected_rentals,       # total cycles expected
            "net_lifetime":       store_net_lifetime,     # total net over all cycles
            "markdown_price":     store_markdown_total,   # alternative: sell now at discount
            "discount_pct":       round(discount_pct * 100, 0),
            "rental_advantage":   store_advantage,        # rental gain over markdown
            "verdict":            verdict,
            "ratio":              ratio,                  # lifetime rental / markdown
        },
    }


# ── ROUTES ─────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/products")
def products():
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(text("""
                SELECT
                    p.product_id,
                    p.product_name,
                    c.category_name,
                    c.depreciation_class,
                    p.original_retail_price,
                    DATEDIFF('2024-12-31', p.listed_date) / 30.44 AS months_unsold
                FROM products p
                JOIN categories c ON p.category_id = c.category_id
                WHERE p.is_active = 1
                  AND c.rental_programme = 1
                ORDER BY c.category_name, p.product_name
                LIMIT 500
            """)).fetchall()

        return jsonify({
            "ok": True,
            "products": [{
                "product_id":    r.product_id,
                "product_name":  r.product_name,
                "category":      r.category_name,
                "dep_class":     r.depreciation_class,
                "retail_price":  float(r.original_retail_price or 0),
                "months_unsold": float(r.months_unsold or 0),
                # Duration rules sent upfront so the slider enforces them on selection
                **(get_appliance_min_days(float(r.original_retail_price or 0))
                   if r.category_name == "Appliances"
                   else MIN_RENTAL_BY_CATEGORY.get(r.category_name, DEFAULT_MIN)),
            } for r in rows]
        })

    except Exception as e:
        print("❌ PRODUCTS ERROR:", e)
        return jsonify({"ok": False, "error": str(e)}), 200


@app.route("/api/customers")
def customers():
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(text("""
                SELECT customer_id, first_name, last_name, customer_segment
                FROM customers
                ORDER BY customer_segment, first_name, last_name
                LIMIT 2000
            """)).fetchall()

        return jsonify({
            "ok": True,
            "customers": [{
                "id":      r.customer_id,
                "name":    " ".join(p for p in [
                               (r.first_name or "").strip(),
                               (r.last_name  or "").strip()
                           ] if p),
                "segment": r.customer_segment or "Unknown",
            } for r in rows]
        })

    except Exception as e:
        print("❌ CUSTOMERS ERROR:", e)
        return jsonify({"ok": False, "error": str(e)}), 200


@app.route("/api/preview", methods=["POST"])
def preview():
    try:
        data = request.json

        with get_engine().connect() as conn:
            prod = conn.execute(text("""
                SELECT
                    p.product_id,
                    p.original_retail_price,
                    c.category_name,
                    c.depreciation_class,
                    DATEDIFF('2024-12-31', p.listed_date) / 30.44 AS months_unsold
                FROM products p
                JOIN categories c ON p.category_id = c.category_id
                WHERE p.product_id = :pid
            """), {"pid": data["product_id"]}).fetchone()

            if not prod:
                return jsonify({"ok": False, "error": "Product not found"}), 200

            price         = float(prod.original_retail_price or 0)
            dep_class     = prod.depreciation_class or "standard"
            category_name = prod.category_name or ""
            months        = float(data.get("months_unsold") or prod.months_unsold or 12)
            rule          = get_pricing_rule(conn, price)

            summary = compute_summary(
                price=price,
                rule=rule,
                days=int(data["duration_days"]),
                qty=int(data["quantity"]),
                months=months,
                dep_class=dep_class,
                category_name=category_name,
            )

        return jsonify({"ok": True, "summary": summary})

    except Exception as e:
        print("❌ PREVIEW ERROR:", e)
        return jsonify({"ok": False, "error": str(e)}), 200


@app.route("/api/submit", methods=["POST"])
def submit():
    try:
        data = request.json

        product_id  = int(data["product_id"])
        customer_id = int(data["customer_id"])
        days        = int(data["duration_days"])
        qty         = int(data["quantity"])

        with get_engine().begin() as conn:
            prod = conn.execute(text("""
                SELECT
                    p.product_id,
                    p.original_retail_price,
                    c.category_name,
                    c.depreciation_class,
                    DATEDIFF('2024-12-31', p.listed_date) / 30.44 AS months_unsold
                FROM products p
                JOIN categories c ON p.category_id = c.category_id
                WHERE p.product_id = :pid
            """), {"pid": product_id}).fetchone()

            if not prod:
                return jsonify({"ok": False, "error": "Product not found"}), 200

            price         = float(prod.original_retail_price or 0)
            dep_class     = prod.depreciation_class or "standard"
            category_name = prod.category_name or ""
            months        = float(data.get("months_unsold") or prod.months_unsold or 12)
            rule          = get_pricing_rule(conn, price)

            if not rule:
                return jsonify({"ok": False, "error": "No pricing rule found"}), 200

            # Server-side minimum duration enforcement
            if category_name == "Appliances":
                min_days = get_appliance_min_days(price)["min_days"]
            else:
                min_days = MIN_RENTAL_BY_CATEGORY.get(category_name, DEFAULT_MIN)["min_days"]
            if days < min_days:
                return jsonify({
                    "ok":    False,
                    "error": f"Minimum rental for {category_name} is {min_days} days",
                }), 200

            summary = compute_summary(
                price=price,
                rule=rule,
                days=days,
                qty=qty,
                months=months,
                dep_class=dep_class,
                category_name=category_name,
            )

            next_id_row = conn.execute(text("""
                SELECT COALESCE(MAX(rental_id), 0) + 1 AS next_id FROM rentals
            """)).fetchone()

            next_rental_id = int(next_id_row.next_id)
            inserted_ids   = []

            for i in range(qty):
                rental_id = next_rental_id + i
                conn.execute(text("""
                    INSERT INTO rentals (
                        rental_id, product_id, customer_id, pricing_rule_id,
                        rental_start_date, rental_end_date,
                        expected_return_date, actual_return_date,
                        rental_duration_days,
                        base_rental_revenue, late_fee, insurance_fee,
                        total_rental_revenue, operational_cost, net_rental_revenue,
                        is_no_return, is_damaged_beyond_repair, is_late
                    ) VALUES (
                        :rental_id, :product_id, :customer_id, :pricing_rule_id,
                        CURDATE(), DATE_ADD(CURDATE(), INTERVAL :days DAY),
                        DATE_ADD(CURDATE(), INTERVAL :days DAY), NULL,
                        :days,
                        :base, :late, :insurance,
                        :gross, :ops, :net,
                        0, 0, 0
                    )
                """), {
                    "rental_id":       rental_id,
                    "product_id":      product_id,
                    "customer_id":     customer_id,
                    "pricing_rule_id": int(rule.rule_id),
                    "days":            days,
                    "base":            summary["base_revenue"],
                    "late":            summary["late_fee_income"],
                    "insurance":       summary["insurance_fee"],
                    "gross":           summary["gross_revenue"],
                    "ops":             summary["ops_cost"],
                    "net":             summary["net_per_unit"],
                })
                inserted_ids.append(rental_id)

        return jsonify({
            "ok":         True,
            "message":    f"{len(inserted_ids)} rental(s) inserted",
            "rental_ids": inserted_ids,
            "summary":    summary,
        })

    except Exception as e:
        print("❌ SUBMIT ERROR:", e)
        return jsonify({"ok": False, "error": str(e)}), 200


@app.route("/api/stats")
def stats():
    """Live stats scoped to rental_programme categories — matches notebook logic."""
    try:
        with get_engine().connect() as conn:
            rental_row = conn.execute(text("""
                SELECT
                    COUNT(*)                             AS total_rentals,
                    ROUND(AVG(total_rental_revenue), 2)  AS avg_revenue
                FROM rentals
            """)).fetchone()

            prog_row = conn.execute(text("""
                SELECT
                    ROUND(AVG(rv.is_rental_more_profitable) * 100, 1) AS win_rate,
                    ROUND(AVG(rv.rental_vs_discount_ratio), 2)         AS avg_ratio
                FROM rental_revenue_vs_discount rv
                JOIN products   p ON rv.product_id  = p.product_id
                JOIN categories c ON p.category_id  = c.category_id
                WHERE c.rental_programme = 1
            """)).fetchone()

        return jsonify({
            "ok":            True,
            "total_rentals": int(rental_row.total_rentals or 0),
            "avg_revenue":   float(rental_row.avg_revenue or 0),
            "win_rate":      float(prog_row.win_rate or 0),
            "avg_ratio":     float(prog_row.avg_ratio or 0),
        })

    except Exception as e:
        print("❌ STATS ERROR:", e)
        return jsonify({
            "ok":            True,
            "total_rentals": 0,
            "avg_revenue":   0,
            "win_rate":      0,
            "avg_ratio":     0,
        })


@app.route("/api/duration_rules")
def duration_rules():
    """All min/friendly duration rules per category — for frontend initialisation."""
    return jsonify({
        "ok":      True,
        "rules":   MIN_RENTAL_BY_CATEGORY,
        "default": DEFAULT_MIN,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5050)
