import json
from collections import defaultdict
from datetime import date, datetime, timedelta

import requests as http_requests
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user

from app import db
from models import FoodLog, CustomFood, WaterLog

food_bp = Blueprint("food", __name__, url_prefix="/food")

OPEN_FOOD_FACTS_SEARCH = (
    "https://world.openfoodfacts.org/cgi/search.pl"
    "?search_terms={q}&action=process&json=1"
    "&fields=product_name,nutriments&page_size=6"
)
OPEN_FOOD_FACTS_BARCODE = "https://world.openfoodfacts.org/api/v0/product/{barcode}.json"

MEAL_ORDER = ["breakfast", "lunch", "dinner", "snacks", "general"]
MEAL_LABELS = {
    "breakfast": "Breakfast",
    "lunch": "Lunch",
    "dinner": "Dinner",
    "snacks": "Snacks",
    "general": "Other",
}


def _extract_nutriments(n):
    return {
        "cal_100g": round(float(n.get("energy-kcal_100g") or n.get("energy-kcal", 0) or 0), 1),
        "protein_100g": round(float(n.get("proteins_100g") or 0), 1),
        "carbs_100g": round(float(n.get("carbohydrates_100g") or 0), 1),
        "fat_100g": round(float(n.get("fat_100g") or 0), 1),
    }


@food_bp.route("/")
@login_required
def log():
    today = date.today()
    entries = FoodLog.query.filter(
        FoodLog.user_id == current_user.id,
        db.func.date(FoodLog.logged_at) == today,
    ).order_by(FoodLog.logged_at).all()

    # Group by meal
    entries_by_meal = defaultdict(list)
    for e in entries:
        meal = e.meal_type or "general"
        entries_by_meal[meal].append(e)

    # Overall totals
    totals = {
        "calories": round(sum(e.calories for e in entries), 1),
        "protein_g": round(sum(e.protein_g for e in entries), 1),
        "carbs_g": round(sum(e.carbs_g for e in entries), 1),
        "fat_g": round(sum(e.fat_g for e in entries), 1),
    }

    # Targets from profile
    profile = current_user.profile
    targets = None
    if profile and profile.calorie_target:
        targets = {
            "calories": int(profile.calorie_target),
            "protein_g": int(profile.protein_target_g),
            "carbs_g": int(profile.carbs_target_g),
            "fat_g": int(profile.fat_target_g),
        }

    # Water today
    water_today = db.session.query(
        db.func.coalesce(db.func.sum(WaterLog.amount_ml), 0)
    ).filter(
        WaterLog.user_id == current_user.id,
        db.func.date(WaterLog.logged_at) == today,
    ).scalar() or 0

    # Weekly data for chart (last 7 days)
    weekly = []
    for i in range(6, -1, -1):
        day_date = today - timedelta(days=i)
        day_entries = FoodLog.query.filter(
            FoodLog.user_id == current_user.id,
            db.func.date(FoodLog.logged_at) == day_date,
        ).all()
        weekly.append({
            "date": day_date.strftime("%a"),
            "calories": round(sum(e.calories for e in day_entries), 1),
            "protein": round(sum(e.protein_g for e in day_entries), 1),
            "carbs": round(sum(e.carbs_g for e in day_entries), 1),
            "fat": round(sum(e.fat_g for e in day_entries), 1),
        })

    # Custom foods for search
    custom_foods = CustomFood.query.filter_by(user_id=current_user.id).order_by(CustomFood.name).all()
    custom_foods_json = json.dumps([
        {"name": cf.name, "cal_100g": cf.cal_100g, "protein_100g": cf.protein_100g,
         "carbs_100g": cf.carbs_100g, "fat_100g": cf.fat_100g, "custom": True}
        for cf in custom_foods
    ])

    return render_template(
        "food/log.html",
        entries_by_meal=dict(entries_by_meal),
        meal_order=MEAL_ORDER,
        meal_labels=MEAL_LABELS,
        totals=totals,
        targets=targets,
        water_today=int(water_today),
        weekly_json=json.dumps(weekly),
        custom_foods_json=custom_foods_json,
    )


@food_bp.route("/add", methods=["POST"])
@login_required
def add():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    required = ["food_name", "serving_g", "cal_100g", "protein_100g", "carbs_100g", "fat_100g"]
    if not all(k in data for k in required):
        return jsonify({"error": "Missing fields"}), 400

    try:
        serving_g = float(data["serving_g"])
        cal_100g = float(data["cal_100g"])
        protein_100g = float(data["protein_100g"])
        carbs_100g = float(data["carbs_100g"])
        fat_100g = float(data["fat_100g"])
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid numeric values"}), 400

    meal_type = data.get("meal_type", "general")
    if meal_type not in MEAL_ORDER:
        meal_type = "general"

    factor = serving_g / 100.0
    entry = FoodLog(
        user_id=current_user.id,
        food_name=str(data["food_name"])[:200],
        serving_g=serving_g,
        calories=round(cal_100g * factor, 1),
        protein_g=round(protein_100g * factor, 1),
        carbs_g=round(carbs_100g * factor, 1),
        fat_g=round(fat_100g * factor, 1),
        meal_type=meal_type,
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify({
        "success": True,
        "entry": {
            "id": entry.id,
            "food_name": entry.food_name,
            "serving_g": entry.serving_g,
            "calories": entry.calories,
            "protein_g": entry.protein_g,
            "carbs_g": entry.carbs_g,
            "fat_g": entry.fat_g,
            "meal_type": entry.meal_type,
        },
    })


@food_bp.route("/delete/<int:entry_id>", methods=["POST"])
@login_required
def delete(entry_id):
    entry = FoodLog.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        return jsonify({"error": "Forbidden"}), 403
    db.session.delete(entry)
    db.session.commit()
    return jsonify({"success": True})


@food_bp.route("/search")
@login_required
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])

    results = []

    # Include matching custom foods first
    q_lower = q.lower()
    custom_foods = CustomFood.query.filter(
        CustomFood.user_id == current_user.id,
        db.func.lower(CustomFood.name).contains(q_lower),
    ).limit(3).all()
    for cf in custom_foods:
        results.append({
            "name": cf.name,
            "cal_100g": cf.cal_100g,
            "protein_100g": cf.protein_100g,
            "carbs_100g": cf.carbs_100g,
            "fat_100g": cf.fat_100g,
            "custom": True,
        })

    # Open Food Facts
    try:
        resp = http_requests.get(
            OPEN_FOOD_FACTS_SEARCH.format(q=http_requests.utils.quote(q)),
            timeout=3,
            headers={"User-Agent": "ForgeFit/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        for product in data.get("products", []):
            name = product.get("product_name", "").strip()
            if not name:
                continue
            n = product.get("nutriments", {})
            results.append({"name": name, "custom": False, **_extract_nutriments(n)})
    except Exception:
        pass

    return jsonify(results[:8])


@food_bp.route("/barcode/<barcode>")
@login_required
def barcode(barcode):
    try:
        resp = http_requests.get(
            OPEN_FOOD_FACTS_BARCODE.format(barcode=barcode),
            timeout=5,
            headers={"User-Agent": "ForgeFit/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return jsonify({"error": "Lookup failed"}), 502

    product = data.get("product")
    if not product or data.get("status") != 1:
        return jsonify({"error": "Product not found"}), 404

    name = product.get("product_name", "").strip() or "Unknown product"
    n = product.get("nutriments", {})
    return jsonify({"name": name, **_extract_nutriments(n)})


@food_bp.route("/custom", methods=["GET"])
@login_required
def list_custom():
    foods = CustomFood.query.filter_by(user_id=current_user.id).order_by(CustomFood.name).all()
    return jsonify([
        {"id": f.id, "name": f.name, "cal_100g": f.cal_100g,
         "protein_100g": f.protein_100g, "carbs_100g": f.carbs_100g, "fat_100g": f.fat_100g}
        for f in foods
    ])


@food_bp.route("/custom", methods=["POST"])
@login_required
def create_custom():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    name = str(data.get("name", "")).strip()[:200]
    if not name:
        return jsonify({"error": "Name required"}), 400
    try:
        food = CustomFood(
            user_id=current_user.id,
            name=name,
            cal_100g=float(data.get("cal_100g", 0)),
            protein_100g=float(data.get("protein_100g", 0)),
            carbs_100g=float(data.get("carbs_100g", 0)),
            fat_100g=float(data.get("fat_100g", 0)),
        )
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid values"}), 400
    db.session.add(food)
    db.session.commit()
    return jsonify({"success": True, "id": food.id, "name": food.name,
                    "cal_100g": food.cal_100g, "protein_100g": food.protein_100g,
                    "carbs_100g": food.carbs_100g, "fat_100g": food.fat_100g})


@food_bp.route("/custom/<int:food_id>", methods=["DELETE"])
@login_required
def delete_custom(food_id):
    food = CustomFood.query.get_or_404(food_id)
    if food.user_id != current_user.id:
        return jsonify({"error": "Forbidden"}), 403
    db.session.delete(food)
    db.session.commit()
    return jsonify({"success": True})


@food_bp.route("/copy-yesterday", methods=["POST"])
@login_required
def copy_yesterday():
    today = date.today()
    yesterday = today - timedelta(days=1)

    yesterday_entries = FoodLog.query.filter(
        FoodLog.user_id == current_user.id,
        db.func.date(FoodLog.logged_at) == yesterday,
    ).all()

    if not yesterday_entries:
        return jsonify({"error": "No entries found for yesterday"}), 404

    new_entries = []
    for e in yesterday_entries:
        new = FoodLog(
            user_id=current_user.id,
            food_name=e.food_name,
            serving_g=e.serving_g,
            calories=e.calories,
            protein_g=e.protein_g,
            carbs_g=e.carbs_g,
            fat_g=e.fat_g,
            meal_type=e.meal_type or "general",
        )
        db.session.add(new)
        new_entries.append(new)

    db.session.commit()

    return jsonify({
        "success": True,
        "count": len(new_entries),
        "entries": [
            {"id": e.id, "food_name": e.food_name, "serving_g": e.serving_g,
             "calories": e.calories, "protein_g": e.protein_g, "carbs_g": e.carbs_g,
             "fat_g": e.fat_g, "meal_type": e.meal_type}
            for e in new_entries
        ],
    })


@food_bp.route("/water", methods=["POST"])
@login_required
def add_water():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    try:
        amount_ml = int(data.get("amount_ml", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid amount"}), 400
    if amount_ml <= 0:
        return jsonify({"error": "Amount must be positive"}), 400

    log = WaterLog(user_id=current_user.id, amount_ml=amount_ml)
    db.session.add(log)
    db.session.commit()

    today = date.today()
    total = db.session.query(
        db.func.coalesce(db.func.sum(WaterLog.amount_ml), 0)
    ).filter(
        WaterLog.user_id == current_user.id,
        db.func.date(WaterLog.logged_at) == today,
    ).scalar() or 0

    return jsonify({"success": True, "total_ml": int(total)})
