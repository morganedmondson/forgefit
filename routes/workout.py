import json

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from models import WorkoutPlan
from ai_engine import generate_plan_with_ai, save_plan_to_db, plan_to_dict

workout_bp = Blueprint("workout", __name__, url_prefix="/workout")


@workout_bp.route("/plan")
@login_required
def plan():
    if not current_user.profile:
        return redirect(url_for("profile.onboarding"))

    # Get latest plan
    latest_plan = WorkoutPlan.query.filter_by(user_id=current_user.id).order_by(
        WorkoutPlan.week_number.desc()
    ).first()

    if not latest_plan:
        flash("No plan found. Let's generate one!", "info")
        return redirect(url_for("profile.onboarding"))

    return render_template("workout/plan.html", plan=latest_plan)


@workout_bp.route("/day/<int:day_index>")
@login_required
def day(day_index):
    latest_plan = WorkoutPlan.query.filter_by(user_id=current_user.id).order_by(
        WorkoutPlan.week_number.desc()
    ).first()

    if not latest_plan:
        return redirect(url_for("profile.onboarding"))

    workout_day = None
    for d in latest_plan.days:
        if d.day_index == day_index:
            workout_day = d
            break

    if not workout_day:
        flash("Day not found.", "error")
        return redirect(url_for("workout.plan"))

    return render_template("workout/day.html", day=workout_day, plan=latest_plan)


@workout_bp.route("/next-week", methods=["POST"])
@login_required
def next_week():
    if not current_user.profile:
        return redirect(url_for("profile.onboarding"))

    latest_plan = WorkoutPlan.query.filter_by(user_id=current_user.id).order_by(
        WorkoutPlan.week_number.desc()
    ).first()

    current_week = latest_plan.week_number if latest_plan else 0
    next_week_num = current_week + 1

    profile = current_user.profile
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

    # Include previous plan for progressive overload
    previous_plan = plan_to_dict(latest_plan) if latest_plan else None

    try:
        plan_data = generate_plan_with_ai(data, week_number=next_week_num, previous_plan=previous_plan)
        save_plan_to_db(current_user.id, next_week_num, plan_data)
        flash(f"Week {next_week_num} plan generated!", "success")
    except Exception as e:
        flash(f"Failed to generate next week: {e}", "error")

    return redirect(url_for("workout.plan"))
