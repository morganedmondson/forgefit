import json
import io
from collections import defaultdict

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, abort
from flask_login import login_required, current_user

from app import db
from models import WorkoutPlan, WorkoutDay, WorkoutLog, Exercise, ExerciseNote
from ai_engine import generate_plan_with_ai, save_plan_to_db, plan_to_dict_with_logs

workout_bp = Blueprint("workout", __name__, url_prefix="/workout")


@workout_bp.route("/plan")
@login_required
def plan():
    if not current_user.profile:
        return redirect(url_for("profile.onboarding"))

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

    # Get existing logs for this day's exercises
    exercise_ids = [ex.id for ex in workout_day.exercises]
    logs = WorkoutLog.query.filter(
        WorkoutLog.exercise_id.in_(exercise_ids),
        WorkoutLog.user_id == current_user.id
    ).all()
    logged_map = {log.exercise_id: log for log in logs}

    # Get user notes for exercises in this day
    exercise_names = [ex.name.lower().strip() for ex in workout_day.exercises]
    user_notes = ExerciseNote.query.filter(
        ExerciseNote.user_id == current_user.id,
        ExerciseNote.exercise_name.in_(exercise_names),
    ).all()
    notes_map = {n.exercise_name: n.note for n in user_notes}

    return render_template(
        "workout/day.html",
        day=workout_day,
        plan=latest_plan,
        logged_map=logged_map,
        notes_map=notes_map,
    )


@workout_bp.route("/log", methods=["POST"])
@login_required
def log_exercise():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    exercise_id = data.get("exercise_id")
    actual_reps = data.get("actual_reps")
    actual_weight_kg = data.get("actual_weight_kg")

    if not all([exercise_id, actual_reps is not None, actual_weight_kg is not None]):
        return jsonify({"error": "Missing fields"}), 400

    exercise = Exercise.query.get(exercise_id)
    if not exercise:
        return jsonify({"error": "Exercise not found"}), 404

    existing = WorkoutLog.query.filter_by(
        exercise_id=exercise_id, user_id=current_user.id
    ).first()

    if existing:
        existing.actual_reps = int(actual_reps)
        existing.actual_weight_kg = float(actual_weight_kg)
    else:
        log = WorkoutLog(
            exercise_id=exercise_id,
            user_id=current_user.id,
            actual_reps=int(actual_reps),
            actual_weight_kg=float(actual_weight_kg),
        )
        db.session.add(log)

    db.session.commit()
    return jsonify({"success": True})


@workout_bp.route("/note", methods=["POST"])
@login_required
def save_note():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    exercise_name = data.get("exercise_name", "").strip().lower()
    note = data.get("note", "").strip()

    if not exercise_name:
        return jsonify({"error": "Missing exercise name"}), 400

    # Upsert: update if exists, create if not
    existing = ExerciseNote.query.filter_by(
        user_id=current_user.id,
        exercise_name=exercise_name,
    ).first()

    if existing:
        existing.note = note
        from datetime import datetime
        existing.updated_at = datetime.utcnow()
    elif note:  # Only create if there's actually a note
        new_note = ExerciseNote(
            user_id=current_user.id,
            exercise_name=exercise_name,
            note=note,
        )
        db.session.add(new_note)

    db.session.commit()
    return jsonify({"success": True})


@workout_bp.route("/progress")
@login_required
def progress():
    logs = db.session.query(WorkoutLog, Exercise).join(
        Exercise, WorkoutLog.exercise_id == Exercise.id
    ).filter(
        WorkoutLog.user_id == current_user.id
    ).order_by(WorkoutLog.logged_at.asc()).all()

    exercise_data = defaultdict(list)
    exercise_names = []
    for log, exercise in logs:
        name = exercise.name
        if name not in exercise_names:
            exercise_names.append(name)
        exercise_data[name].append({
            "date": log.logged_at.strftime("%Y-%m-%d"),
            "weight": log.actual_weight_kg,
            "reps": log.actual_reps,
        })

    return render_template(
        "workout/progress.html",
        exercise_names=exercise_names,
        exercise_data=json.dumps(dict(exercise_data)),
    )


@workout_bp.route("/export-pdf")
@login_required
def export_pdf():
    from fpdf import FPDF

    latest_plan = WorkoutPlan.query.filter_by(user_id=current_user.id).order_by(
        WorkoutPlan.week_number.desc()
    ).first()

    if not latest_plan:
        flash("No plan to export.", "error")
        return redirect(url_for("workout.plan"))

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 15, f"ForgeFit - Week {latest_plan.week_number}", ln=True, align="C")
    pdf.ln(5)

    for day_obj in latest_plan.days:
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(0, 10, day_obj.label, ln=True, fill=True)
        pdf.ln(2)

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(80, 8, "Exercise", border=1)
        pdf.cell(25, 8, "Sets", border=1, align="C")
        pdf.cell(25, 8, "Reps", border=1, align="C")
        pdf.cell(35, 8, "Weight (kg)", border=1, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 10)
        for ex in day_obj.exercises:
            pdf.cell(80, 8, ex.name[:35], border=1)
            pdf.cell(25, 8, str(ex.sets), border=1, align="C")
            pdf.cell(25, 8, str(ex.reps), border=1, align="C")
            pdf.cell(35, 8, str(ex.weight_kg), border=1, align="C")
            pdf.ln()

        pdf.ln(5)

    pdf_bytes = pdf.output()
    buffer = io.BytesIO(pdf_bytes)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"forgefit_week_{latest_plan.week_number}.pdf",
    )


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
    # Fetch all user exercise notes for AI context
    all_notes = ExerciseNote.query.filter_by(user_id=current_user.id).all()
    exercise_notes = {n.exercise_name: n.note for n in all_notes}

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
        "exercise_notes": exercise_notes,
    }

    previous_plan = plan_to_dict_with_logs(latest_plan, current_user.id) if latest_plan else None

    try:
        plan_data = generate_plan_with_ai(data, week_number=next_week_num, previous_plan=previous_plan)
        save_plan_to_db(current_user.id, next_week_num, plan_data)
        flash(f"Week {next_week_num} plan generated!", "success")
    except Exception as e:
        flash(f"Failed to generate next week: {e}", "error")

    return redirect(url_for("workout.plan"))


@workout_bp.route("/session/<int:day_id>")
@login_required
def session(day_id):
    day = WorkoutDay.query.get_or_404(day_id)
    if day.plan.user_id != current_user.id:
        abort(403)

    # Existing logs for today
    exercise_ids = [ex.id for ex in day.exercises]
    logs = WorkoutLog.query.filter(
        WorkoutLog.exercise_id.in_(exercise_ids),
        WorkoutLog.user_id == current_user.id,
    ).all()
    logged_map = {log.exercise_id: log for log in logs}

    # Personal notes
    exercise_names = [ex.name.lower().strip() for ex in day.exercises]
    user_notes = ExerciseNote.query.filter(
        ExerciseNote.user_id == current_user.id,
        ExerciseNote.exercise_name.in_(exercise_names),
    ).all()
    notes_map = {n.exercise_name: n.note for n in user_notes}

    exercises_data = []
    for ex in day.exercises:
        log = logged_map.get(ex.id)
        exercises_data.append({
            "id": ex.id,
            "name": ex.name,
            "sets": ex.sets,
            "reps": ex.reps,
            "weight_kg": ex.weight_kg,
            "muscle_group": ex.muscle_group or "",
            "notes": ex.notes or "",
            "user_note": notes_map.get(ex.name.lower().strip(), ""),
            "logged_reps": log.actual_reps if log else ex.reps,
            "logged_weight": log.actual_weight_kg if log else ex.weight_kg,
        })

    return render_template(
        "workout/session.html",
        day=day,
        exercises_json=json.dumps(exercises_data),
        plan_url=url_for("workout.plan"),
    )
