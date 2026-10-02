import time
from threading import Lock

from flask import Blueprint, current_app, render_template, request, flash, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required
from app.models import Usuario
from app import db
from app.utils import format_bolivian_phone

auth = Blueprint('auth', __name__)

# --- Proteccion basica contra fuerza bruta (en memoria, suficiente para un
#     despliegue local mono-proceso). Bloquea por CI + IP tras varios fallos. ---
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 300  # 5 minutos
_FAILED_ATTEMPTS = {}
_ATTEMPTS_LOCK = Lock()

# Hash ficticio para igualar el tiempo de respuesta cuando el CI no existe
# (evita un oraculo de temporizacion que delate que usuarios estan registrados).
_DUMMY_HASH = generate_password_hash('dummy-password-for-timing-equalization')


def _attempt_key():
    ci = (request.form.get('ci') or '').strip().lower()
    return f'{request.remote_addr or "?"}|{ci}'


def _is_locked(key):
    with _ATTEMPTS_LOCK:
        record = _FAILED_ATTEMPTS.get(key)
        if not record:
            return False
        count, first_ts = record
        if (time.time() - first_ts) >= _LOCKOUT_SECONDS:
            _FAILED_ATTEMPTS.pop(key, None)
            return False
        return count >= _MAX_ATTEMPTS


def _register_failure(key):
    with _ATTEMPTS_LOCK:
        count, first_ts = _FAILED_ATTEMPTS.get(key, (0, time.time()))
        if (time.time() - first_ts) >= _LOCKOUT_SECONDS:
            count, first_ts = 0, time.time()
        _FAILED_ATTEMPTS[key] = (count + 1, first_ts)


def _clear_failures(key):
    with _ATTEMPTS_LOCK:
        _FAILED_ATTEMPTS.pop(key, None)


@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        key = _attempt_key()

        if _is_locked(key):
            flash('Demasiados intentos fallidos. Espera unos minutos e intenta de nuevo.', 'warning')
            return render_template('auth/login.html')

        ci = (request.form.get('ci') or '').strip()
        password = request.form.get('password') or ''

        user = Usuario.query.filter_by(ci=ci).first()

        # Cuenta no activada: unico mensaje especifico que conservamos por UX de
        # onboarding. No revela la contrasena ni permite distinguir un fallo de login.
        if user and not user.cuenta_activa:
            flash('Necesitas activar tu cuenta primero', 'warning')
            return redirect(url_for('auth.register'))

        # Siempre ejecutamos una verificacion de hash (real o ficticia) para no
        # filtrar por tiempo si el CI existe o no.
        stored_hash = user.password if user else _DUMMY_HASH
        password_ok = check_password_hash(stored_hash, password)

        if user and password_ok:
            _clear_failures(key)
            login_user(user)
            return redirect(url_for('admin.dashboard'))

        _register_failure(key)
        flash('CI o contraseña incorrectos', 'danger')

    return render_template('auth/login.html')


@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        ci = (request.form.get('ci') or '').strip()
        password = request.form.get('password') or ''
        telefono = format_bolivian_phone(request.form.get('telefono'))

        usuario = Usuario.query.filter_by(ci=ci).first()

        # No se permite activar cuentas administrativas por la via publica:
        # cierra la toma de control de admin conociendo solo el CI.
        if not usuario or usuario.cuenta_activa or usuario.es_admin:
            flash('CI no encontrado o cuenta ya activada', 'warning')
            return redirect(url_for('auth.register'))

        if len(password) < 8:
            flash('La contraseña debe tener al menos 8 caracteres.', 'warning')
            return redirect(url_for('auth.register'))

        usuario.password = generate_password_hash(password)
        if telefono:
            usuario.telefono = telefono
        usuario.cuenta_activa = True
        db.session.commit()

        flash('Cuenta activada exitosamente', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('public.index'))


@auth.route('/dev-login')
def dev_login():
    if not (current_app.debug or current_app.config.get('ENABLE_DEV_LOGIN')):
        return redirect(url_for('auth.login'))
    if request.remote_addr not in ('127.0.0.1', '::1', 'localhost'):
        return redirect(url_for('auth.login'))
    admin_user = Usuario.query.filter_by(es_admin=True).first()
    if admin_user:
        login_user(admin_user)
        return redirect(url_for('admin.dashboard'))
    return redirect(url_for('auth.login'))
