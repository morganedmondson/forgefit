from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app import db
from models import WorkoutPlan
from ai_engine import chat_with_ai, save_plan_to_db

chat_bp = Blueprint("chat", __name__, url_prefix="/api")


@chat_bp.route("/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "No message provided"}), 400

    message = data["message"].strip()
    if not message:
        return jsonify({"error": "Empty message"}), 400

    latest_plan = WorkoutPlan.query.filter_by(user_id=current_user.id).order_by(
        WorkoutPlan.week_number.desc()
    ).first()

    profile = current_user.profile

    try:
        reply, plan_data = chat_with_ai(message, latest_plan, profile)

        plan_updated = False
        if plan_data and latest_plan:
            # Delete the old plan's days/exercises and replace with modified plan
            for day in latest_plan.days:
                db.session.delete(day)
            db.session.flush()

            from models import WorkoutDay, Exercise
            for day_data in plan_data:
                day = WorkoutDay(
                    plan_id=latest_plan.id,
                    day_index=day_data["day_index"],
                    label=day_data["label"],
                )
                db.session.add(day)
                db.session.flush()

                for i, ex_data in enumerate(day_data.get("exercises", [])):
                    exercise = Exercise(
                        day_id=day.id,
                        order=i,
                        name=ex_data["name"],
                        sets=int(ex_data["sets"]),
                        reps=int(ex_data["reps"]),
                        weight_kg=float(ex_data["weight_kg"]),
                        is_compound=bool(ex_data.get("is_compound", False)),
                        notes=ex_data.get("notes", ""),
                    )
                    db.session.add(exercise)

            db.session.commit()
            plan_updated = True

        return jsonify({"reply": reply, "plan_updated": plan_updated})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
