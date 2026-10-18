from app.utils import get_bolivia_time, local_redirect_target
import platform
import secrets
import sys
import traceback

from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, logout_user
from werkzeug.security import check_password_hash

from app import db
from app.models import Prestamo, ProductoVenta, Usuario, Configuracion, Venta
from app.services.database_service import create_backup, database_path, restore_backup
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
from app.utils.themes import DESIGN_STYLES, THEMES


@admin.route('/hacer-respaldo', methods=['POST'])
@login_required
@admin_required
def hacer_respaldo():
    try:
        backup_path = create_backup()
        flash(f'Respaldo creado exitosamente: {backup_path}', 'success')
    except Exception as exc:
        flash(f'Error al crear el respaldo: {exc}', 'danger')
        traceback.print_exc()

    return redirect(local_redirect_target(request.referrer, url_for('admin.configuracion'), origin=request.host_url))


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
        backup_actual = restore_backup(backup_path)
        Configuracion.set_valor('session_epoch', secrets.token_urlsafe(24))
        logout_user()
        session.clear()
        flash(
            'Respaldo restaurado correctamente. '
            f'Se guardo una copia previa en: {backup_actual}',
            'success',
        )
        return redirect(url_for('auth.login'))
    except Exception as exc:
        flash(f'No se pudo restaurar el respaldo: {exc}', 'danger')
        traceback.print_exc()

    return redirect(url_for('admin.configuracion'))


@admin.route('/panel/<key>')
@login_required
@admin_required
def admin_panel(key):
    if key != current_app.config['ADMIN_URL_KEY']:
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

                Configuracion.set_valor('interes_maximo', str(maximo), commit=False)
                Configuracion.set_valor('interes_prendario', str(prendario), commit=False)
                db.session.commit()
                flash(
                    'Tasas guardadas correctamente. '
                    f'Interés prendario: {prendario}%, Máximo permitido: {maximo}%.',
                    'success',
                )
            except ValueError as exc:
                flash(str(exc), 'danger')
        elif accion == 'cambiar_tema':
            tema = request.form.get('tema')
            estilo = request.form.get('estilo', Configuracion.get_valor('estilo_sistema', 'flat'))
            if tema in THEMES and estilo in DESIGN_STYLES:
                Configuracion.set_valor('tema_sistema', tema, commit=False)
                Configuracion.set_valor('estilo_sistema', estilo, commit=False)
                db.session.commit()
                flash(f'Diseño guardado: {DESIGN_STYLES[estilo]["name"]} · {THEMES[tema]["name"]}.', 'success')
                return redirect(url_for('admin.configuracion', _anchor='apariencia'))
            else:
                flash('Tema o estilo no válido.', 'danger')
        elif accion == 'cambiar_whatsapp':
            auto_envio = 'true' if request.form.get('whatsapp_auto_envio') == 'on' else 'false'
            Configuracion.set_valor('whatsapp_auto_envio', auto_envio)
            if auto_envio == 'true':
                flash('Modo de WhatsApp: Envío 100% automático activado al registrar pagos.', 'success')
            else:
                flash('Modo de WhatsApp: Confirmación previa activada (se preguntará con ventana emergente).', 'info')

    total_usuarios = Usuario.query.count()
    total_prestamos = Prestamo.query.count()
    total_productos = ProductoVenta.query.count()

    total_prestado = db.session.query(db.func.sum(Prestamo.monto_prestado)).filter_by(estado='activo').scalar() or 0.0

    ventas = Venta.query.all()
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
        'backup_dir': current_app.config['BACKUP_DIR'],
        'db_path': str(database_path()) if db.engine.url.database != ':memory:' else ':memory:',
    }

    tema_actual = Configuracion.get_valor('tema_sistema', 'default')
    whatsapp_auto_envio = Configuracion.get_valor('whatsapp_auto_envio', 'true') == 'true'
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
        design_styles=DESIGN_STYLES,
        tema_actual=tema_actual,
        whatsapp_auto_envio=whatsapp_auto_envio,
    )
