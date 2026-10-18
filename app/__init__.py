import os
import secrets
from flask import Flask, abort, flash, g, redirect, request, session, url_for
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
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
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
    migrate.init_app(app, db, directory=os.path.join(os.path.dirname(app.root_path), 'migrations'))
    login_manager.login_view = 'auth.login'
    from app.services.database_gate import DatabaseGate
    app.extensions['database_lock'] = DatabaseGate()

    @app.before_request
    def coordinate_database_access():
        exclusive = request.endpoint in {'admin.restaurar_respaldo', 'admin.whatsapp_toggle_enabled'}
        gate = app.extensions['database_lock']
        gate.acquire_exclusive() if exclusive else gate.acquire()
        g._database_lock_held = 'exclusive' if exclusive else 'shared'
        financial_writes = {'admin.registrar_pago', 'admin.vender_producto', 'admin.cambiar_estado',
                            'admin.decomisar_a_inventario', 'admin.nuevo_prestamo',
                            'admin.prestamo_anterior', 'auth.configurar_admin', 'auth.register',
                            'admin.editar_prestamo', 'admin.editar_usuario', 'admin.editar_producto',
                            'admin.nuevo_producto', 'admin.eliminar_producto', 'admin.poner_en_venta',
                            'admin.configuracion', 'admin.whatsapp_toggle_auto',
                            'admin.whatsapp_toggle_enabled', 'client.actualizar_perfil'}
        writes = request.method == 'POST' and request.endpoint in financial_writes
        writes = writes or request.method == 'GET' and request.endpoint in {'admin.dashboard', 'admin.ver_prestamo'}
        if writes and db.engine.dialect.name == 'sqlite':
            # Reservar la escritura antes de leer saldo/stock también entre procesos.
            connection = db.session.connection()
            if not connection.connection.driver_connection.in_transaction:
                connection.exec_driver_sql('BEGIN IMMEDIATE')

    @app.teardown_request
    def release_database_access(error=None):
        db.session.remove()
        mode = g.pop('_database_lock_held', None)
        if mode == 'exclusive':
            app.extensions['database_lock'].release_exclusive()
        elif mode:
            app.extensions['database_lock'].release()

    with app.app_context():
        from app.models.articulo import Articulo
        from app.models.prestamo import Prestamo
        from app.models.producto import ProductoVenta
        from app.models.usuario import Usuario
        from app.models.configuracion import Configuracion
        from app.utils.themes import DESIGN_STYLES, THEMES

        @app.context_processor
        def inject_theme():
            from app.services.whatsapp_service import esta_habilitado
            tema_key = Configuracion.get_valor('tema_sistema', 'default')
            tema = THEMES.get(tema_key, THEMES['default'])
            estilo = Configuracion.get_valor('estilo_sistema', 'flat')
            return {
                'tema_actual_key': tema_key if tema_key in THEMES else 'default',
                'tema_actual_vars': tema['variables'],
                'tema_actual_dark': tema.get('is_dark', False),
                'estilo_actual': estilo if estilo in DESIGN_STYLES else 'flat',
                'whatsapp_habilitado': esta_habilitado(),
            }

        for folder in [app.config['UPLOAD_FOLDER'], app.config['BACKUP_DIR']]:
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError:
                pass

        from app.routes.admin import admin
        from app.routes.auth import auth
        from app.routes.client import client
        from app.routes.public import public

        app.register_blueprint(auth)
        app.register_blueprint(admin, url_prefix=app.config['ADMIN_PREFIX'])
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
            return {'csrf_token': generate_csrf_token, 'operation_token': lambda: secrets.token_urlsafe(24)}

        @app.before_request
        def protect_from_csrf():
            # Las pruebas pueden deshabilitar CSRF explícitamente; TESTING no lo omite.
            if not app.config.get('CSRF_ENABLED', True):
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
            from app.utils import local_redirect_target
            return redirect(local_redirect_target(request.referrer, url_for('public.index'), origin=request.host_url))

        @login_manager.user_loader
        def load_user(user_id):
            try:
                from app.models import Configuracion
                if session.get('auth_epoch') != Configuracion.get_valor('session_epoch', 'initial'):
                    return None
                user = db.session.get(Usuario, int(user_id))
                return user if user and user.cuenta_activa else None
            except (TypeError, ValueError):
                return None

        @app.errorhandler(404)
        def not_found_error(error):
            from flask import render_template
            return render_template('errors/404.html'), 404

        @app.errorhandler(500)
        def internal_error(error):
            from flask import render_template
            db.session.rollback()
            return render_template('errors/500.html'), 500

        if not app.config.get('TESTING'):
            from app.services.database_service import initialize_database
            initialize_database()

        return app
