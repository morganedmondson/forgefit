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

    return app
