from datetime import date, datetime

import requests as http_requests
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user

from app import db
from models import FoodLog

food_bp = Blueprint("food", __name__, url_prefix="/food")

OPEN_FOOD_FACTS_URL = (
    "https://world.openfoodfacts.org/cgi/search.pl"
    "?search_terms={q}&action=process&json=1"
    "&fields=product_name,nutriments&page_size=6"
)


@food_bp.route("/")
@login_required
def log():
    today = date.today()
    entries = FoodLog.query.filter(
        FoodLog.user_id == current_user.id,
        db.func.date(FoodLog.logged_at) == today,
    ).order_by(FoodLog.logged_at).all()

    totals = {
        "calories": round(sum(e.calories for e in entries), 1),
        "protein_g": round(sum(e.protein_g for e in entries), 1),
        "carbs_g": round(sum(e.carbs_g for e in entries), 1),
        "fat_g": round(sum(e.fat_g for e in entries), 1),
    }

    return render_template("food/log.html", entries=entries, totals=totals)


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

    factor = serving_g / 100.0
    entry = FoodLog(
        user_id=current_user.id,
        food_name=str(data["food_name"])[:200],
        serving_g=serving_g,
        calories=round(cal_100g * factor, 1),
        protein_g=round(protein_100g * factor, 1),
        carbs_g=round(carbs_100g * factor, 1),
        fat_g=round(fat_100g * factor, 1),
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

    try:
        resp = http_requests.get(
            OPEN_FOOD_FACTS_URL.format(q=http_requests.utils.quote(q)),
            timeout=3,
            headers={"User-Agent": "ForgeFit/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return jsonify([])

    results = []
    for product in data.get("products", []):
        name = product.get("product_name", "").strip()
        if not name:
            continue
        n = product.get("nutriments", {})
        results.append({
            "name": name,
            "cal_100g": round(float(n.get("energy-kcal_100g") or n.get("energy-kcal", 0) or 0), 1),
            "protein_100g": round(float(n.get("proteins_100g") or 0), 1),
            "carbs_100g": round(float(n.get("carbohydrates_100g") or 0), 1),
            "fat_100g": round(float(n.get("fat_100g") or 0), 1),
        })

    return jsonify(results[:6])
