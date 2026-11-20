from pathlib import Path
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_apscheduler import APScheduler
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
scheduler = APScheduler()

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Inicia sesión para continuar."
    migrate.init_app(app, db)
    csrf.init_app(app)
    from app import models
    from app.routes import main, auth, api
    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp, url_prefix="/auth")
    app.register_blueprint(api.bp, url_prefix="/api")

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify(error="Solicitud inválida"), 400

    @app.errorhandler(404)
    def not_found(error):
        if app.request_class and app.config.get("TESTING"):
            return jsonify(error="No encontrado"), 404
        return "No encontrado", 404

    with app.app_context():
        db.create_all()
        from app.services.alerts import generate_alerts
        if not app.config.get("TESTING"):
            scheduler.init_app(app)
            scheduler.start()
            if not scheduler.get_job("daily-alerts"):
                def scheduled_alerts():
                    with app.app_context():
                        generate_alerts()
                scheduler.add_job(id="daily-alerts", func=scheduled_alerts, trigger="interval", hours=6)
    return app
