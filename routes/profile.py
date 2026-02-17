from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from models import Profile, WorkoutPlan
from ai_engine import generate_plan_with_ai, save_plan_to_db

profile_bp = Blueprint("profile", __name__, url_prefix="/profile")


@profile_bp.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    if request.method == "POST":
        try:
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
            }
        except (KeyError, ValueError):
            flash("Please fill in all fields with valid numbers.", "error")
            return render_template("profile/onboarding.html")

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
            profile.height_cm = float(request.form["height_cm"])
            profile.weight_kg = float(request.form["weight_kg"])
            profile.goal = request.form["goal"]
            profile.plan_type = request.form["plan_type"]
            profile.days_per_week = int(request.form["days_per_week"])
            profile.squat_1rm = float(request.form["squat_1rm"])
            profile.bench_1rm = float(request.form["bench_1rm"])
            profile.deadlift_1rm = float(request.form["deadlift_1rm"])
            profile.ohp_1rm = float(request.form["ohp_1rm"])
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
        }

        try:
            plan_data = generate_plan_with_ai(data, week_number=1)
            save_plan_to_db(current_user.id, 1, plan_data)
            flash("Profile updated and plan regenerated!", "success")
        except Exception as e:
            flash(f"Plan generation failed: {e}", "error")

        return redirect(url_for("workout.plan"))

    return render_template("profile/onboarding.html", profile=current_user.profile, editing=True)
