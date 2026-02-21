import os
from pathlib import Path

from flask import Flask, redirect, url_for, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user

db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # Render/Supabase provide postgres:// but SQLAlchemy needs postgresql://
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + str(
            Path(__file__).parent / "forgefit.db"
        )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from routes import register_blueprints
    register_blueprints(app)

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            if current_user.profile:
                return redirect(url_for("workout.plan"))
            return redirect(url_for("profile.onboarding"))
        return render_template("index.html")

    with app.app_context():
        db.create_all()
        _migrate_db()

    return app


def _migrate_db():
    """Add new columns to existing tables without dropping data."""
    from sqlalchemy import text
    migrations = [
        "ALTER TABLE profile ADD COLUMN gym_equipment VARCHAR(100) DEFAULT ''",
        "ALTER TABLE exercise ADD COLUMN muscle_group VARCHAR(30) DEFAULT ''",
        # Feature 1: macro goals
        "ALTER TABLE profile ADD COLUMN age INTEGER",
        "ALTER TABLE profile ADD COLUMN sex VARCHAR(10)",
        "ALTER TABLE profile ADD COLUMN activity_level VARCHAR(20) DEFAULT 'moderate'",
        "ALTER TABLE profile ADD COLUMN calorie_target FLOAT DEFAULT 0",
        "ALTER TABLE profile ADD COLUMN protein_target_g FLOAT DEFAULT 0",
        "ALTER TABLE profile ADD COLUMN carbs_target_g FLOAT DEFAULT 0",
        "ALTER TABLE profile ADD COLUMN fat_target_g FLOAT DEFAULT 0",
        # Feature 2: meal type on food log
        "ALTER TABLE food_log ADD COLUMN meal_type VARCHAR(20) DEFAULT 'general'",
    ]
    for sql in migrations:
        try:
            with db.engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception:
            pass  # Column already exists
