from .auth import auth_bp
from .profile import profile_bp
from .workout import workout_bp
from .chat import chat_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(workout_bp)
    app.register_blueprint(chat_bp)
