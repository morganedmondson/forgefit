from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    profile = db.relationship("Profile", backref="user", uselist=False, cascade="all, delete-orphan")
    plans = db.relationship("WorkoutPlan", backref="user", cascade="all, delete-orphan", order_by="WorkoutPlan.week_number.desc()")
    food_logs = db.relationship("FoodLog", backref="user", cascade="all, delete-orphan")
    exercise_notes = db.relationship("ExerciseNote", backref="user", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    height_cm = db.Column(db.Float, nullable=False)
    weight_kg = db.Column(db.Float, nullable=False)
    goal = db.Column(db.String(20), nullable=False)  # muscle, strength, general
    plan_type = db.Column(db.String(30), nullable=False)  # push_pull_legs, upper_lower, full_body, menstrual_cycle, bro_split
    days_per_week = db.Column(db.Integer, nullable=False)
    squat_1rm = db.Column(db.Float, nullable=False)
    bench_1rm = db.Column(db.Float, nullable=False)
    deadlift_1rm = db.Column(db.Float, nullable=False)
    ohp_1rm = db.Column(db.Float, nullable=False)
    gym_equipment = db.Column(db.String(100), default="")


class WorkoutPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    days = db.relationship("WorkoutDay", backref="plan", cascade="all, delete-orphan", order_by="WorkoutDay.day_index")


class WorkoutDay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("workout_plan.id"), nullable=False)
    day_index = db.Column(db.Integer, nullable=False)
    label = db.Column(db.String(50), nullable=False)

    exercises = db.relationship("Exercise", backref="day", cascade="all, delete-orphan", order_by="Exercise.order")


class Exercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day_id = db.Column(db.Integer, db.ForeignKey("workout_day.id"), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    sets = db.Column(db.Integer, nullable=False)
    reps = db.Column(db.Integer, nullable=False)
    weight_kg = db.Column(db.Float, nullable=False)
    is_compound = db.Column(db.Boolean, default=False)
    notes = db.Column(db.String(200), default="")
    muscle_group = db.Column(db.String(30), default="")

    logs = db.relationship("WorkoutLog", backref="exercise", cascade="all, delete-orphan")


class WorkoutLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercise.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    actual_reps = db.Column(db.Integer, nullable=False)
    actual_weight_kg = db.Column(db.Float, nullable=False)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow)


class ExerciseNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    exercise_name = db.Column(db.String(100), nullable=False)  # normalised lowercase
    note = db.Column(db.String(500), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("user_id", "exercise_name"),)


class FoodLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    food_name = db.Column(db.String(200), nullable=False)
    serving_g = db.Column(db.Float, nullable=False)
    calories = db.Column(db.Float, nullable=False)
    protein_g = db.Column(db.Float, nullable=False)
    carbs_g = db.Column(db.Float, nullable=False)
    fat_g = db.Column(db.Float, nullable=False)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow)
