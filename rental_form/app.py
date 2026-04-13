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

# ── Pricing / business assumptions ─────────────
OPS_COST = 0.185
DAMAGE = 0.028

def choose_pricing_model(price: float) -> str:
    if price > 500:
        return "pct_of_retail"
    return "flat_rate"

def get_pricing_rule(conn, price: float):
    pricing_model = choose_pricing_model(price)
    return conn.execute(text("""
        SELECT
            rule_id,
            pricing_model,
            base_daily_rate,
            pct_of_retail_daily,
            late_fee_per_day,
            insurance_fee_pct
        FROM pricing_rules
        WHERE pricing_model = :pm
        ORDER BY rule_id
        LIMIT 1
    """), {"pm": pricing_model}).fetchone()

def estimate_expected_rentals(months_unsold: float, price: float) -> int:
    # Items are already around 1 year old, so future rental potential is modest
    if months_unsold < 3:
        expected = 5
    elif months_unsold < 6:
        expected = 4
    elif months_unsold < 9:
        expected = 3
    elif months_unsold < 12:
        expected = 2
    else:
        expected = 2

    # Expensive items usually rent fewer times
    if price > 1500:
        expected -= 1
    elif price < 250:
        expected += 1

    return max(2, min(expected, 5))

def compute_summary(price: float, rule, days: int, qty: int, months: float):
    if rule is None:
        raise ValueError("No pricing rule found")

    if rule.pricing_model == "pct_of_retail":
        daily_rate = float(price) * float(rule.pct_of_retail_daily or 0)
    else:
        daily_rate = float(rule.base_daily_rate or 0)

    base = daily_rate * days
    insurance = base * float(rule.insurance_fee_pct or 0)
    late = 0.0
    gross = base + insurance + late
    ops = gross * OPS_COST
    damage = price * DAMAGE
    net = gross - ops - damage

    # Markdown adjusted to max 70% of retail
    if months < 3:
        markdown = price * 0.70
    elif months < 6:
        markdown = price * 0.60
    elif months < 9:
        markdown = price * 0.45
    elif months < 12:
        markdown = price * 0.35
    else:
        markdown = price * 0.25

    expected_rentals = estimate_expected_rentals(months, price)

    # Only part of theoretical demand is realized
    utilization_rate = 0.67

    lifetime_rental_value = net * expected_rentals * utilization_rate
    verdict = "rental" if lifetime_rental_value > markdown else "markdown"

    ratio = round(lifetime_rental_value / markdown, 2) if markdown else 0
    delta = round((lifetime_rental_value - markdown) * qty, 2)

    return {
        "daily_rate": round(daily_rate, 2),
        "base_revenue": round(base, 2),
        "insurance_fee": round(insurance, 2),
        "late_fee_income": round(late, 2),
        "gross_revenue": round(gross, 2),
        "ops_cost": round(ops, 2),
        "damage_cost": round(damage, 2),
        "net_per_unit": round(net, 2),
        "total_net": round(net * qty, 2),
        "markdown_price": round(markdown, 2),
        "total_markdown": round(markdown * qty, 2),
        "expected_rentals": expected_rentals,
        "utilization_rate": utilization_rate,
        "lifetime_rental_value": round(lifetime_rental_value, 2),
        "ratio": ratio,
        "delta": delta,
        "verdict": verdict,
        "retail_price": round(price, 2),
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
                    p.original_retail_price,
                    DATEDIFF(CURDATE(), p.listed_date)/30.44 AS months_unsold
                FROM products p
                JOIN categories c ON p.category_id = c.category_id
                WHERE p.is_active = 1
                ORDER BY c.category_name, p.product_name
                LIMIT 500
            """)).fetchall()

        return jsonify({
            "ok": True,
            "products": [{
                "product_id": r.product_id,
                "product_name": r.product_name,
                "category": r.category_name,
                "retail_price": float(r.original_retail_price or 0),
                "rule_type": "auto",
                "monthly_amount": 0,
                "months_unsold": float(r.months_unsold or 0)
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
                "id": r.customer_id,
                "name": " ".join(
                    part for part in [(r.first_name or "").strip(), (r.last_name or "").strip()]
                    if part
                ),
                "segment": r.customer_segment or "Unknown"
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
                    product_id,
                    original_retail_price
                FROM products
                WHERE product_id = :pid
            """), {"pid": data["product_id"]}).fetchone()

            if not prod:
                return jsonify({"ok": False, "error": "Product not found"}), 200

            price = float(prod.original_retail_price or 0)
            rule = get_pricing_rule(conn, price)

            summary = compute_summary(
                price=price,
                rule=rule,
                days=int(data["duration_days"]),
                qty=int(data["quantity"]),
                months=float(data.get("months_unsold", 12))
            )

        return jsonify({"ok": True, "summary": summary})

    except Exception as e:
        print("❌ PREVIEW ERROR:", e)
        return jsonify({"ok": False, "error": str(e)}), 200

@app.route("/api/submit", methods=["POST"])
def submit():
    try:
        data = request.json

        product_id = int(data["product_id"])
        customer_id = int(data["customer_id"])
        days = int(data["duration_days"])
        qty = int(data["quantity"])
        months_unsold = float(data.get("months_unsold", 12))

        with get_engine().begin() as conn:
            prod = conn.execute(text("""
                SELECT
                    product_id,
                    original_retail_price
                FROM products
                WHERE product_id = :pid
            """), {"pid": product_id}).fetchone()

            if not prod:
                return jsonify({"ok": False, "error": "Product not found"}), 200

            price = float(prod.original_retail_price or 0)
            rule = get_pricing_rule(conn, price)

            if not rule:
                return jsonify({"ok": False, "error": "No pricing rule found"}), 200

            summary = compute_summary(
                price=price,
                rule=rule,
                days=days,
                qty=qty,
                months=months_unsold
            )

            next_id_row = conn.execute(text("""
                SELECT COALESCE(MAX(rental_id), 0) + 1 AS next_id
                FROM rentals
            """)).fetchone()

            next_rental_id = int(next_id_row.next_id)
            inserted_ids = []

            for i in range(qty):
                rental_id = next_rental_id + i

                conn.execute(text("""
                    INSERT INTO rentals (
                        rental_id,
                        product_id,
                        customer_id,
                        pricing_rule_id,
                        rental_start_date,
                        rental_end_date,
                        expected_return_date,
                        actual_return_date,
                        rental_duration_days,
                        base_rental_revenue,
                        late_fee,
                        insurance_fee,
                        total_rental_revenue,
                        operational_cost,
                        net_rental_revenue,
                        is_no_return,
                        is_damaged_beyond_repair,
                        is_late
                    ) VALUES (
                        :rental_id,
                        :product_id,
                        :customer_id,
                        :pricing_rule_id,
                        CURDATE(),
                        DATE_ADD(CURDATE(), INTERVAL :days DAY),
                        DATE_ADD(CURDATE(), INTERVAL :days DAY),
                        NULL,
                        :days,
                        :base,
                        :late,
                        :insurance,
                        :gross,
                        :ops,
                        :net,
                        0,
                        0,
                        0
                    )
                """), {
                    "rental_id": rental_id,
                    "product_id": product_id,
                    "customer_id": customer_id,
                    "pricing_rule_id": int(rule.rule_id),
                    "days": days,
                    "base": summary["base_revenue"],
                    "late": summary["late_fee_income"],
                    "insurance": summary["insurance_fee"],
                    "gross": summary["gross_revenue"],
                    "ops": summary["ops_cost"],
                    "net": summary["net_per_unit"],
                })

                inserted_ids.append(rental_id)

        return jsonify({
            "ok": True,
            "message": f"{len(inserted_ids)} rental(s) inserted",
            "rental_ids": inserted_ids,
            "summary": summary
        })

    except Exception as e:
        print("❌ SUBMIT ERROR:", e)
        return jsonify({"ok": False, "error": str(e)}), 200

@app.route("/api/stats")
def stats():
    try:
        with get_engine().connect() as conn:
            row = conn.execute(text("""
                SELECT
                    COUNT(*) AS total_rentals,
                    ROUND(AVG(total_rental_revenue), 2) AS avg_revenue
                FROM rentals
            """)).fetchone()

        return jsonify({
            "ok": True,
            "total_rentals": int(row.total_rentals or 0),
            "avg_revenue": float(row.avg_revenue or 0),
            "win_rate": 0,
            "avg_ratio": 0
        })

    except Exception as e:
        print("❌ STATS ERROR:", e)
        return jsonify({
            "ok": True,
            "total_rentals": 0,
            "avg_revenue": 0,
            "win_rate": 0,
            "avg_ratio": 0
        })

if __name__ == "__main__":
    app.run(debug=True, port=5050)