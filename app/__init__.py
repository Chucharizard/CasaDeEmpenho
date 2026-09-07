import os
import secrets
from flask import Flask, abort, flash, redirect, request, session, url_for
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass


def create_app(test_config=None):
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(Config)

    # Permite sobreescribir configuración en tests (TESTING=True, BD en memoria, etc.)
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    login_manager.login_view = 'auth.login'

    with app.app_context():
        from app.models.articulo import Articulo
        from app.models.prestamo import Prestamo
        from app.models.producto import ProductoVenta
        from app.models.usuario import Usuario
        from app.models.configuracion import Configuracion
        from app.utils.themes import THEMES

        @app.context_processor
        def inject_theme():
            tema_key = Configuracion.get_valor('tema_sistema', 'default')
            tema = THEMES.get(tema_key, THEMES['default'])
            return {
                'tema_actual_key': tema_key,
                'tema_actual_vars': tema['variables'],
                'tema_actual_dark': tema.get('is_dark', False)
            }

        for folder in [Config.UPLOAD_FOLDER, Config.BACKUP_DIR]:
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError:
                pass

        from app.routes.admin import admin
        from app.routes.auth import auth
        from app.routes.client import client
        from app.routes.public import public

        app.register_blueprint(auth)
        app.register_blueprint(admin)
        app.register_blueprint(client)
        app.register_blueprint(public)

        def generate_csrf_token():
            token = session.get('_csrf_token')
            if not token:
                token = secrets.token_urlsafe(32)
                session['_csrf_token'] = token
            return token

        @app.context_processor
        def inject_csrf_token():
            return {'csrf_token': generate_csrf_token}

        @app.before_request
        def protect_from_csrf():
            # En modo testing se omite la validación CSRF para poder hacer POSTs
            if app.config.get('TESTING'):
                return None

            if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
                return None
            if (request.endpoint or '').startswith('static'):
                return None

            session_token = session.get('_csrf_token')
            request_token = request.form.get('csrf_token') or request.headers.get('X-CSRFToken')

            if session_token and request_token and secrets.compare_digest(session_token, request_token):
                return None

            if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
                abort(400, description='CSRF token invalido')

            flash('La sesion del formulario expiro. Intenta nuevamente.', 'danger')
            return redirect(request.referrer or url_for('public.index'))

        try:
            from app.sync.sync_triggers import setup_sync_triggers
            setup_sync_triggers(app)
            app.logger.info('Sistema de sincronizacion activado')
        except ImportError:
            app.logger.info('Modulo de sincronizacion no disponible')
        except Exception as exc:
            app.logger.warning('Error al activar sincronizacion: %s', exc)

        try:
            from app.routes.sync_routes import sync_bp
            app.register_blueprint(sync_bp)
            app.logger.info('Rutas de sincronizacion registradas')
        except ImportError:
            pass
        except Exception as exc:
            app.logger.warning('Error al registrar rutas de sync: %s', exc)

        @login_manager.user_loader
        def load_user(user_id):
            return db.session.get(Usuario, int(user_id))

        @app.errorhandler(404)
        def not_found_error(error):
            from flask import render_template
            return render_template('errors/404.html'), 404

        @app.errorhandler(500)
        def internal_error(error):
            from flask import render_template
            db.session.rollback()
            return render_template('errors/500.html'), 500

        return app
