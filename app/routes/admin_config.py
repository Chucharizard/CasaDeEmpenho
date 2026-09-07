from app.utils import get_bolivia_time
import os
import platform
import shutil
import sys
import traceback

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.security import check_password_hash

from app import db
from app.models import Prestamo, ProductoVenta, Usuario, Configuracion
from app.models.articulo import Articulo
from app.routes.admin_shared import (
    admin,
    admin_required,
    get_safe_backup_path,
    get_tasa_configurada,
    list_backup_files,
    parse_interest,
    parse_positive_float,
    MAX_ALLOWED_INTEREST,
)
from app.utils.themes import THEMES
from config import Config


@admin.route('/hacer-respaldo', methods=['POST'])
@login_required
@admin_required
def hacer_respaldo():
    try:
        os.makedirs(Config.BACKUP_DIR, exist_ok=True)
        fecha = get_bolivia_time().strftime('%Y-%m-%d_%H-%M-%S')
        backup_path = os.path.join(Config.BACKUP_DIR, f'backup_{fecha}.db')

        if not os.path.exists(Config.SQLITE_DB_PATH):
            flash(f'No se encontro la base de datos en: {Config.SQLITE_DB_PATH}', 'danger')
            return redirect(url_for('admin.configuracion'))

        shutil.copyfile(Config.SQLITE_DB_PATH, backup_path)
        flash(f'Respaldo creado exitosamente: {backup_path}', 'success')
    except Exception as exc:
        flash(f'Error al crear el respaldo: {exc}', 'danger')
        traceback.print_exc()

    return redirect(request.referrer or url_for('admin.configuracion'))


@admin.route('/restaurar-respaldo', methods=['POST'])
@login_required
@admin_required
def restaurar_respaldo():
    backup_name = request.form.get('backup_name')
    password = request.form.get('password_confirmacion')

    if not password or not check_password_hash(current_user.password, password):
        flash('Contrasena incorrecta. No se restauro el respaldo.', 'danger')
        return redirect(url_for('admin.configuracion'))

    backup_path = get_safe_backup_path(backup_name)
    if not backup_path:
        flash('El respaldo seleccionado no es valido.', 'danger')
        return redirect(url_for('admin.configuracion'))

    try:
        fecha = get_bolivia_time().strftime('%Y-%m-%d_%H-%M-%S')
        backup_actual = os.path.join(Config.BACKUP_DIR, f'pre_restore_{fecha}.db')
        os.makedirs(Config.BACKUP_DIR, exist_ok=True)

        if os.path.exists(Config.SQLITE_DB_PATH):
            shutil.copyfile(Config.SQLITE_DB_PATH, backup_actual)

        db.session.remove()
        db.engine.dispose()
        shutil.copyfile(backup_path, Config.SQLITE_DB_PATH)
        flash(
            'Respaldo restaurado correctamente. '
            f'Se guardo una copia previa en: {backup_actual}',
            'success',
        )
    except Exception as exc:
        flash(f'No se pudo restaurar el respaldo: {exc}', 'danger')
        traceback.print_exc()

    return redirect(url_for('admin.configuracion'))


@admin.route('/panel/<key>')
@login_required
@admin_required
def admin_panel(key):
    if key != Config.ADMIN_URL_KEY:
        return redirect(url_for('public.index'))

    prestamos_activos = [prestamo for prestamo in current_user.prestamos if prestamo.estado == 'activo']
    total_usuarios = Usuario.query.count()
    total_prestamos = Prestamo.query.count()
    total_articulos = db.session.query(db.func.count(Articulo.id)).scalar() or 0

    return render_template(
        'client/panel.html',
        prestamos=prestamos_activos,
        total_usuarios=total_usuarios,
        total_prestamos=total_prestamos,
        total_articulos=total_articulos,
    )


@admin.route('/configuracion', methods=['GET', 'POST'])
@login_required
@admin_required
def configuracion():
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'cambiar_interes':
            try:
                maximo = parse_positive_float(request.form.get('interes_maximo'), 'interes maximo')
                prendario = parse_interest(request.form.get('interes_prendario'), max_allowed=maximo)

                Configuracion.set_valor('interes_maximo', str(maximo))
                Configuracion.set_valor('interes_prendario', str(prendario))
                flash(
                    'Tasas guardadas correctamente. '
                    f'Interés prendario: {prendario}%, Máximo permitido: {maximo}%.',
                    'success',
                )
            except ValueError as exc:
                flash(str(exc), 'danger')
        elif accion == 'cambiar_tema':
            tema = request.form.get('tema')
            if tema in THEMES:
                Configuracion.set_valor('tema_sistema', tema)
                flash(f'Tema actualizado a: {THEMES[tema]["name"]}', 'success')
            else:
                flash('Tema no valido.', 'danger')

    total_usuarios = Usuario.query.count()
    total_prestamos = Prestamo.query.count()
    total_productos = ProductoVenta.query.count()

    total_prestado = db.session.query(db.func.sum(Prestamo.monto_prestado)).filter_by(estado='activo').scalar() or 0.0

    ventas = ProductoVenta.query.filter_by(estado='vendido').all()
    total_invertido = db.session.query(
        db.func.sum(ProductoVenta.precio_compra * ProductoVenta.stock)
    ).filter(
        ProductoVenta.estado.in_(['compra', 'disponible']),
        ProductoVenta.precio_compra.isnot(None),
    ).scalar() or 0
    total_vendido = sum(venta.precio for venta in ventas)

    sistema_info = {
        'python_version': sys.version.split(' ')[0],
        'plataforma': platform.system(),
        'arquitectura': platform.machine(),
        'fecha_actual': get_bolivia_time().strftime('%d/%m/%Y %H:%M:%S'),
        'backup_dir': Config.BACKUP_DIR,
        'db_path': Config.SQLITE_DB_PATH,
    }

    tema_actual = Configuracion.get_valor('tema_sistema', 'default')
    tasas = {
        'prendario': get_tasa_configurada('interes_prendario', 10.0),
        'maximo': get_tasa_configurada('interes_maximo', MAX_ALLOWED_INTEREST),
    }

    return render_template(
        'admin/configuracion.html',
        tasas=tasas,
        total_usuarios=total_usuarios,
        total_prestamos=total_prestamos,
        total_prestamos_prendarios=total_prestamos,
        total_productos=total_productos,
        total_prestado=total_prestado,
        total_prestado_prendario=total_prestado,
        total_invertido=total_invertido,
        total_vendido=total_vendido,
        sistema_info=sistema_info,
        backups=list_backup_files(),
        themes=THEMES,
        tema_actual=tema_actual
    )
