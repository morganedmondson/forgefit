from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from models import Profile, WorkoutPlan
from ai_engine import generate_plan_with_ai, save_plan_to_db

profile_bp = Blueprint("profile", __name__, url_prefix="/profile")

ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}


def calculate_macro_targets(weight_kg, height_cm, age, sex, activity_level, goal):
    """Mifflin-St Jeor BMR -> TDEE -> macro splits. Returns dict or None."""
    if not age or not sex:
        return None
    if sex == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

    tdee = bmr * ACTIVITY_MULTIPLIERS.get(activity_level or "moderate", 1.55)

    if goal == "muscle":
        calories = tdee + 300
        protein = weight_kg * 2.2
        fat = weight_kg * 0.9
    elif goal == "strength":
        calories = tdee + 200
        protein = weight_kg * 2.0
        fat = weight_kg * 1.0
    else:  # general
        calories = tdee
        protein = weight_kg * 1.6
        fat = weight_kg * 0.8

    carbs = max(0, (calories - protein * 4 - fat * 9) / 4)
    return {
        "calorie_target": round(calories),
        "protein_target_g": round(protein),
        "carbs_target_g": round(carbs),
        "fat_target_g": round(fat),
    }


@profile_bp.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    if request.method == "POST":
        try:
            age_raw = request.form.get("age", "").strip()
            data = {
                "height_cm": float(request.form["height_cm"]),
                "weight_kg": float(request.form["weight_kg"]),
                "goal": request.form["goal"],
                "plan_type": request.form["plan_type"],
                "days_per_week": int(request.form["days_per_week"]),
                "squat_1rm": float(request.form["squat_1rm"]),
                "bench_1rm": float(request.form["bench_1rm"]),
                "deadlift_1rm": float(request.form["deadlift_1rm"]),
                "ohp_1rm": float(request.form["ohp_1rm"]),
                "gym_equipment": request.form.get("gym_equipment", "").strip(),
                "age": int(age_raw) if age_raw else None,
                "sex": request.form.get("sex") or None,
                "activity_level": request.form.get("activity_level", "moderate"),
            }
        except (KeyError, ValueError):
            flash("Please fill in all fields with valid numbers.", "error")
            return render_template("profile/onboarding.html")

        # Calculate macro targets if age + sex provided
        targets = calculate_macro_targets(
            data["weight_kg"], data["height_cm"], data["age"],
            data["sex"], data["activity_level"], data["goal"]
        )
        if targets:
            data.update(targets)

        # Create or update profile
        profile = current_user.profile
        if profile:
            for key, val in data.items():
                setattr(profile, key, val)
        else:
            profile = Profile(user_id=current_user.id, **data)
            db.session.add(profile)

        db.session.commit()

        # Generate week 1 plan via Claude
        try:
            plan_data = generate_plan_with_ai(data, week_number=1)
            save_plan_to_db(current_user.id, 1, plan_data)
            flash("Your training plan has been generated!", "success")
        except Exception as e:
            flash(f"Plan generation failed: {e}. Please try again.", "error")
            return redirect(url_for("profile.onboarding"))

        return redirect(url_for("workout.plan"))

    return render_template("profile/onboarding.html")


@profile_bp.route("/edit", methods=["GET", "POST"])
@login_required
def edit():
    if not current_user.profile:
        return redirect(url_for("profile.onboarding"))

    if request.method == "POST":
        try:
            profile = current_user.profile
            age_raw = request.form.get("age", "").strip()
            profile.height_cm = float(request.form["height_cm"])
            profile.weight_kg = float(request.form["weight_kg"])
            profile.goal = request.form["goal"]
            profile.plan_type = request.form["plan_type"]
            profile.days_per_week = int(request.form["days_per_week"])
            profile.squat_1rm = float(request.form["squat_1rm"])
            profile.bench_1rm = float(request.form["bench_1rm"])
            profile.deadlift_1rm = float(request.form["deadlift_1rm"])
            profile.ohp_1rm = float(request.form["ohp_1rm"])
            profile.gym_equipment = request.form.get("gym_equipment", "").strip()
            profile.age = int(age_raw) if age_raw else None
            profile.sex = request.form.get("sex") or None
            profile.activity_level = request.form.get("activity_level", "moderate")

            # Recalculate macro targets
            targets = calculate_macro_targets(
                profile.weight_kg, profile.height_cm, profile.age,
                profile.sex, profile.activity_level, profile.goal
            )
            if targets:
                profile.calorie_target = targets["calorie_target"]
                profile.protein_target_g = targets["protein_target_g"]
                profile.carbs_target_g = targets["carbs_target_g"]
                profile.fat_target_g = targets["fat_target_g"]

            db.session.commit()
        except (KeyError, ValueError):
            flash("Please fill in all fields with valid numbers.", "error")
            return render_template("profile/onboarding.html", profile=current_user.profile, editing=True)

        # Regenerate plan with new profile
        data = {
            "height_cm": profile.height_cm,
            "weight_kg": profile.weight_kg,
            "goal": profile.goal,
            "plan_type": profile.plan_type,
            "days_per_week": profile.days_per_week,
            "squat_1rm": profile.squat_1rm,
            "bench_1rm": profile.bench_1rm,
            "deadlift_1rm": profile.deadlift_1rm,
            "ohp_1rm": profile.ohp_1rm,
            "gym_equipment": profile.gym_equipment or "",
        }

        try:
            plan_data = generate_plan_with_ai(data, week_number=1)
            save_plan_to_db(current_user.id, 1, plan_data)
            flash("Profile updated and plan regenerated!", "success")
        except Exception as e:
            flash(f"Plan generation failed: {e}", "error")

        return redirect(url_for("workout.plan"))

    return render_template("profile/onboarding.html", profile=current_user.profile, editing=True)
